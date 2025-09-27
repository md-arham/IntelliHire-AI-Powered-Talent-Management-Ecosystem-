from uuid import UUID, uuid4
from app.database.models.employer_profiles_models import EmployerProfile
from fastapi import Depends, HTTPException, Query
from qdrant_client.http.models import Distance, PointStruct, VectorParams
from sentence_transformers import util
from sqlalchemy import desc, and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.database.models.resume_versions_models import ResumeVersion
from app.database.db import get_db
from app.database.models import (
    JobCandidateMatching,
    JobCandidateScreening,
    Student,
    ResumeScreeningInternship,
    ResumeScreeningResult,
)
from app.database.models.job_postings_models import JobPosting
from app.database.models import PersonalInfo
from app.services.user_service import get_structured_resume_data
from app.utils.settings import (
    embedding_model,
    settings,
    qdrant_client,
)
from app.utils.summarize_descriptions import summarize_jobs_with_llm
from app.utils.logger_config import logger
from sqlalchemy.exc import SQLAlchemyError
from app.utils.get_matching_reason import get_strengths_and_gaps

COLLECTION_NAME = settings.JOB_COLLECTION_NAME
RESUME_COLLECTION = settings.RESUMES_COLLECTION_NAME
VECTOR_SIZE = settings.VECTOR_SIZE
SIMILARITY_THRESHOLD = settings.RECOMMENDATION_SIMILARITY_THRESHOLD

# Store resume vector
async def job_vectorStore(job_id_to_fetch: UUID, db: AsyncSession):
    """
    Summarize and store the job description vector into Qdrant for similarity search.

    Args:
        job_id_to_fetch (UUID): UUID of the job to be processed.
        db (AsyncSession): Asynchronous database session.

    Returns:
        dict: Message and extracted summary JSON.

    Raises:
        Exception: If vector storage or JSON parsing fails.
    """

    collections = await qdrant_client.get_collections()  # CHANGED: await
    if COLLECTION_NAME not in [
        col.name for col in collections.collections
    ]:  # CHANGED: collections.collections
        await qdrant_client.recreate_collection(  # CHANGED: await
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )

    job_screening_result = await db.execute(
        select(JobPosting).where(JobPosting.job_id == job_id_to_fetch)
    )
    job_posting = job_screening_result.scalars().first()

    # Early return if job not found
    if not job_posting:
        logger.warning(f"[VectorStore] No job found for job_id={job_id_to_fetch}")
        return {
            "message": f"No job found for job_id={job_id_to_fetch}. Vector storage skipped.",
            "summary": None
        }

    # Extract job posting fields
    title = job_posting.title
    description = job_posting.description
    location = job_posting.location
    required_skills = job_posting.required_skills or []
    min_experience = job_posting.min_experience
    additional_info = job_posting.additional_info

    # Step 5: Format the resume data
    skills_text = ", ".join([skill for skill in required_skills])

    combined_job_data = (
        f"Job Tile: {title}"
        f"Description: {description}"
        f"Skills: {skills_text}\n"
        f"Experience: {min_experience}\n"
        f"Location: {location}"
        f"additional_info : {additional_info}"
    )

    logger.info(f"Combined DB Job Data: {combined_job_data}")

    # Step 6: Summarize and encode
    job_data = await summarize_jobs_with_llm(combined_job_data)
    logger.info(f"LLM Summary for JD: {job_data}")

    skills = (
        job_data.get("skills") or title or "general"
    )  # encodes the skills as " " and encodes something meaninful
    vector = embedding_model.encode(skills, normalize_embeddings=False)

    # Step 7: Create Qdrant point and upsert

    point = PointStruct(
        id=str(job_id_to_fetch),
        vector=vector.tolist(),
        payload={"Job_id": str(job_id_to_fetch), "summary": job_data},
    )
    logger.info(f"Job Point to store: {point}")

    await qdrant_client.upsert(  # CHANGED: await
        collection_name=COLLECTION_NAME, points=[point]
    )

    return {
        "message": f"Job data summarised for the job_id: {job_id_to_fetch}",
        "summary": job_data,
    }


async def recommend_candidates(job_id: UUID, db: AsyncSession):
    """
    Recommend candidate resumes for a given job by comparing vector similarity and field matches.

    Args:
        job_id (UUID): UUID of the job for which candidates are to be recommended.
        db (AsyncSession): Asynchronous database session.

    Returns:
        dict: Contains job ID, screening ID, and list of matched student resume IDs.

    Raises:
        Exception: If vector retrieval, similarity matching, or database insertion fails.
    """
    logger.info(f"Recommending candidates for job_id: {job_id}")

    # Step 2: Fetch Job_id vector from Qdrant
    try:
        retrieved = await qdrant_client.retrieve(  # CHANGED: await
            collection_name=COLLECTION_NAME, ids=[str(job_id)], with_vectors=True
        )
        if not retrieved:
            logger.warning(f"No vector found for job_id={job_id}")
            return {str(job_id): []}

        job_point = retrieved[0]
        job_vector = job_point.vector
        job_payload = job_point.payload.get("summary", {})
        job_skills = job_payload.get("skills","")
        logger.info(f"Retrieved vector & payload for job_id={job_id}")

    except Exception as e:
        logger.exception(f"Error while retrieving Job vector: {e}")
        return {"error": "Failed to retrieve Job vector"}

    # Step 3: Scroll all resume vectors
    try:
        all_candidates, _ = await qdrant_client.scroll(
            collection_name=RESUME_COLLECTION,
            with_vectors=True,
            with_payload=True,
            limit=10000,
        )
        logger.info(f"Retrieved {len(all_candidates)} candidate resumes from Qdrant")
    except Exception as e:
        logger.exception(f"Failed to scroll resume vectors: {e}")
        return {"error": "resume vector fetch failed"}

    # Step 4: Similarity check
    matched_student_ids = []
    similarity_scores = []
    matching_details = []
    for candidate in all_candidates:
        student_exists_result = await db.execute(
            select(Student).where(Student.student_id == candidate.id)
        )
        student_exists = student_exists_result.scalars().first()

        if student_exists:
            similarity = util.cos_sim(job_vector, candidate.vector).item()
            logger.info(f"Matching score: {similarity}")
            if similarity >= SIMILARITY_THRESHOLD:
                candidate_payload = candidate.payload.get("summary", {})
                if check_payload_match(job_payload, candidate_payload):
                    matched_student_ids.append(candidate.id)
                    logger.info(f"student_id: {candidate.id}")
                    similarity_scores.append(round(similarity * 100, 2))
                    candidate_fields = extract_matching_fields(candidate_payload)

                    candidate_skills = candidate_payload.get("skills", "")
                    matching_skills, missing_skills = get_strengths_and_gaps(
                        resume_skills_str=candidate_skills,
                        job_skills_str=job_skills
                    )

                    matching_details.append({
                        "fields": candidate_fields,
                        "matching_skills": matching_skills,
                        "missing_skills": missing_skills,
                    })

    logger.info(f"Matched {len(matched_student_ids)} student resumes")

    try:
        screening_id = uuid4()
        job_posting_result = await db.execute(
            select(JobPosting).where(JobPosting.job_id == job_id)
        )
        job_posting = job_posting_result.scalars().first()

        if not job_posting:
            logger.warning(f"JobPosting not found for job_id={job_id}")
            return {"error": "JobPosting not found"}

        employer_id = job_posting.employer_id

        # Create screening record
        screening = JobCandidateScreening(
            screening_id=screening_id, employer_id=employer_id, job_id=job_id
        )
        db.add(screening)
        await db.commit()
        logger.info(f"Screening result committed with ID: {screening_id}")

        # Create matching records
        for student_id, score, detail_bundle in zip(
            matched_student_ids, similarity_scores, matching_details
        ):
            details = detail_bundle["fields"]
            matching_skills = detail_bundle["matching_skills"]
            missing_skills = detail_bundle["missing_skills"]

            resume_version_result = await db.execute(
                select(ResumeVersion).where(ResumeVersion.student_id == student_id)
            )
            resume_version = resume_version_result.scalars().first()

            if not resume_version:
                logger.warning(
                    f"ResumeVersion not found for student_id {student_id} during matching insertion"
                )
                continue
            version_id = resume_version.version_id

            matching = JobCandidateMatching(
                screening_id=screening_id,
                student_id=student_id,
                version_id=version_id,
                matching_score=score,
                matching_skills=matching_skills,
                missing_skills=missing_skills,
                degree_qualification=details.get("degree_qualification"),
                college_name=details.get("college_name"),
                branch=details.get("branch"),
                passed_out_year=details.get("passed_out_year"),
                grade=details.get("grade"),
                college_type=details.get("college_type"),
                location=details.get("location"),
            )
            db.add(matching)

            # Fetch ResumeScreeningResult for student
            resume_screening_result = await db.execute(
                select(ResumeScreeningResult).where(
                    ResumeScreeningResult.student_id == student_id
                )
            )

            resume_screening = resume_screening_result.scalars().first()

            if not resume_screening:
                logger.warning(f"No ResumeScreeningResult for student_id {student_id}")
                continue

            # Insert into ResumeScreeningInternship
            new_entry = ResumeScreeningInternship(
                screening_id=resume_screening.screening_id,
                internship_id=job_id,
                matching_score=score,
                matching_skills=matching_skills,
                missing_skills=missing_skills,
                source="Internal",
            )
            await db.merge(new_entry)  # Use merge to avoid duplicate PK conflicts

        await db.commit()
        logger.info(
            f"Matching Candidates committed with screening_id: {screening_id} and added this job to the candidate in internshiprecommnedation table"
        )

    except Exception as e:
        await db.rollback()
        logger.exception(f"Failed to store screening and matching records: {e}")
        return {"error": "Failed to store screening and matching records"}

    return {
        "Job_id": str(job_id),
        "screening_id": str(screening_id),
        "matched_resumes": [str(sid) for sid in matched_student_ids],
    }


def check_payload_match(job_payload, candidate_payload):
    """
    Compare job and candidate payloads to determine if key fields match.

    Args:
        job_payload (dict): Extracted structured data from job description.
        candidate_payload (dict): Extracted structured data from candidate resume.

    Returns:
        bool: True if candidate matches the job requirements, False otherwise.
    """
    logger.info(f"Job Payload: {job_payload}")
    logger.info(f"candidate Payload: {candidate_payload}")
    fields = ["college_type", "branch", "passed_out_year", "grade"]
    for field in fields:
        job_value = job_payload.get(field)
        candidate_value = candidate_payload.get(field)
        if job_value is None or job_value == "":
            continue
        if field == "passed_out_year":
            if isinstance(job_value, list):
                if candidate_value not in job_value:
                    return False
            else:
                if candidate_value != job_value:
                    return False
        elif field == "grade":
            try:
                if float(candidate_value) < float(job_value):
                    return False
            except Exception:
                return False
        else:
            if isinstance(job_value, str) and isinstance(candidate_value, str):
                if job_value.lower() != candidate_value.lower():
                    return False
            else:
                if job_value != candidate_value:
                    return False
    return True


MATCH_FIELDS = [
    "degree_qualification",
    "college_type",
    "branch",
    "passed_out_year",
    "location",
    "grade",
    "college_name",
]


def extract_matching_fields(payload):
    """
    Extract only the predefined matching fields from a candidate payload.

    Args:
        payload (dict): Structured resume data.

    Returns:
        dict: Dictionary containing only matching fields.
    """
    return {field: payload.get(field) for field in MATCH_FIELDS}


async def get_matchedresumes_for_job(job_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Retrieve matched resumes for a given job based on screening results.

    This function fetches all screening records associated with the provided job ID,
    then retrieves all matched students along with their matching scores and structured resume data.
    The resumes are sorted based on matching scores in descending order.

    Args:
        job_id (UUID): The unique identifier for the job posting.
        db (AsyncSession, optional): The database session dependency injected by FastAPI.

    Returns:
        List[dict]: A list of dictionaries containing structured resume data for each matched candidate,
                    including their matching score.

    Raises:
        HTTPException: If no screenings are found for the given job ID.
        HTTPException: If any error occurs during database operations or resume data retrieval.
    """
    try:
        # 1. Fetch all screening entries for the given job_id
        screening_result = await db.execute(
            select(JobCandidateScreening).where(JobCandidateScreening.job_id == job_id)
        )
        screenings = screening_result.scalars().all()
        if not screenings:
            raise HTTPException(
                status_code=404, detail="No screenings found for this job"
            )

        result = []
        for screening in screenings:
            # 2. For each screening, fetch all matches (student_id & matching_score)
            matches_result = await db.execute(
                select(JobCandidateMatching)
                .where(JobCandidateMatching.screening_id == screening.screening_id)
                .order_by(desc(JobCandidateMatching.matching_score))
            )
            matches = matches_result.scalars().all()

            for match in matches:
                # 3. Get user_id from Student table using student_id
                student_result = await db.execute(
                    select(Student).where(Student.student_id == match.student_id)
                )
                student = student_result.scalar_one_or_none() 

                if not student:
                    logger.warning(
                        f"Student not found for student_id {match.student_id}"
                    )
                    continue
                user_id = student.user_id

                try:
                    # 4. Get structured resume data using user_id
                    resume_data = await get_structured_resume_data(user_id, db)
                    resume_data["matching_score"] = match.matching_score
                    resume_data["matching_skills"] = match.matching_skills
                    resume_data["missing_skills"] = match.missing_skills
                    result.append(resume_data)  #
                except HTTPException as e:
                    logger.warning(
                        f"Failed to get resume for user {user_id}: {e.detail}"
                    )
                    continue
                except Exception as e:
                    logger.error(f"Unexpected error for user {user_id}: {str(e)}")
                    continue

        return result

    except Exception as e:
        logger.error(f"Failed to process job_id {job_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail="An error occurred while processing the request"
        )


async def get_filtered_matchedresumes_for_job(
    job_id: UUID,
    degree_qualification: Optional[str] = Query(None),
    branch: Optional[str] = Query(None),
    passed_out_year: Optional[int] = Query(None),
    grade: Optional[float] = Query(None),
    college_type: Optional[str] = Query(None),
    matching_score: Optional[float] = Query(None),
    country: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve resumes matched to a job with additional filtering applied.

    Args:
        job_id (UUID): UUID of the job posting.
        filters (dict): Dictionary of filtering criteria (e.g., grade, branch, location).
        db (AsyncSession): Asynchronous database session.

    Returns:
        List[dict]: List of structured resume data matching the job and filters.

    Raises:
        HTTPException: If job screening data or matches are not found.
    """
    try:
        screening_result = await db.execute(
            select(JobCandidateScreening).where(JobCandidateScreening.job_id == job_id)
        )
        screenings = screening_result.scalars().all()

        if not screenings:
            raise HTTPException(
                status_code=404, detail="No screenings found for this job"
            )

        result = []

        for screening in screenings:
            # Build dynamic filters
            filters = [JobCandidateMatching.screening_id == screening.screening_id]

            if degree_qualification:
                filters.append(
                    JobCandidateMatching.degree_qualification == degree_qualification
                )
            if branch:
                filters.append(JobCandidateMatching.branch == branch)
            if passed_out_year:
                filters.append(JobCandidateMatching.passed_out_year == passed_out_year)
            if grade:
                filters.append(JobCandidateMatching.grade >= grade)
            if college_type:
                filters.append(JobCandidateMatching.college_type == college_type)
            if matching_score is not None:
                filters.append(JobCandidateMatching.matching_score >= matching_score)

            # Apply filters to the query
            matches_result = await db.execute(
                select(JobCandidateMatching)
                .where(and_(*filters))
                .order_by(desc(JobCandidateMatching.matching_score))
            )
            matches = matches_result.scalars().all()

            # Filter matches based on country and region from PersonalInfo
            filtered_matches = []
            for match in matches:
                personal_info_result = await db.execute(
                    select(PersonalInfo).where(
                        PersonalInfo.student_id == match.student_id
                    )
                )
                personal_info = personal_info_result.scalars().first()
                if not personal_info or not personal_info.location:
                    if country or region:
                        continue  # Skip if location is required but missing
                    else:
                        filtered_matches.append(match)
                        continue

                # Split location into country and region
                location_parts = personal_info.location.split(",", 1)  # Split only once
                location_country = location_parts[0].strip() if len(location_parts) > 0 else None
                location_region = location_parts[1].strip() if len(location_parts) > 1 else None

                country_match = country is None or (
                    location_country and location_country == country
                )
                region_match = region is None or (
                    location_region and location_region == region
                )

                if country_match and region_match:
                    filtered_matches.append(match)

            for match in filtered_matches:
                student_result = await db.execute(
                    select(Student).where(Student.student_id == match.student_id)
                )
                student = student_result.scalars().first()
                if not student:
                    logger.warning(
                        f"Student not found for student_id {match.student_id}"
                    )
                    continue

                user_id = student.user_id

                try:
                    resume_data = await get_structured_resume_data(user_id, db)
                    resume_data["matching_score"] = match.matching_score
                    resume_data["matching_skills"] = match.matching_skills
                    resume_data["missing_skills"] = match.missing_skills
                    result.append(resume_data)
                except HTTPException as e:
                    logger.warning(
                        f"Failed to get resume for user {user_id}: {e.detail}"
                    )
                    continue
                except Exception as e:
                    logger.error(f"Unexpected error for user {user_id}: {str(e)}")
                    continue

        return result

    except Exception as e:
        logger.error(f"Failed to process job_id {job_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail="An error occurred while processing the request"
        )
    

async def get_top_candidate_matches_service(user_id: UUID, db: AsyncSession):
    try:
        # Step 1: Fetch employer_id from user_id
        result = await db.execute(
            select(EmployerProfile).where(EmployerProfile.user_id == user_id)
        )
        employer = result.scalars().first()
        if not employer:
            raise HTTPException(status_code=404, detail="Employer not found")

        employer_id = employer.employer_id

        # Step 2: Fetch all job postings by this employer
        result = await db.execute(
            select(JobPosting).where(JobPosting.employer_id == employer_id)
        )
        job_postings = result.scalars().all()
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching employer or job postings: {e}")
        raise HTTPException(status_code=500, detail="Database error occurred while fetching employer or job postings")

    top_matches = []
    for job in job_postings:
        try:
            result = await db.execute(
                select(JobCandidateMatching)
                .join(
                    JobCandidateScreening,
                    JobCandidateMatching.screening_id == JobCandidateScreening.screening_id,
                )
                .where(JobCandidateScreening.job_id == job.job_id)
                .order_by(JobCandidateMatching.matching_score.desc())
            )
            top_match = result.scalars().first()

            if top_match:
                result = await db.execute(
                    select(Student).where(Student.student_id == top_match.student_id)
                )
                student = result.scalars().first()

                if student:
                    try:
                        matched_student = await get_structured_resume_data(student.user_id, db)
                    except Exception as e:
                        logger.error(f"Failed to fetch structured resume for student {student.student_id}: {e}")
                        continue
                    matched_student["match_score"] = top_match.matching_score
                    matched_student["job_title"] = job.title
                    matched_student["job_id"] = str(job.job_id)
                    top_matches.append(matched_student)

            logger.info(f"Matched student {student.student_id} to job {job.job_id}")
        except Exception as e:
            logger.error(f"Error processing job_id {job.job_id}: {e}")
            continue

    return top_matches