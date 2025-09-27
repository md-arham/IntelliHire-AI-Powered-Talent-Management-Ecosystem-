from uuid import UUID, uuid4
from datetime import datetime
import asyncio
from qdrant_client.http.models import Distance, PointStruct, VectorParams
from fastapi import HTTPException
from sentence_transformers import util
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Optional
from app.database.models import (
    Education,
    PersonalInfo,
    ResumeScreeningInternship,
    ResumeScreeningResult,
    ResumeVersion,
    Skill,
    Student,
    JobPosting,
    JobCandidateScreening,
    JobCandidateMatching,
)
from app.schemas.resume_schemas import ResumeSummary
from app.utils.settings import (
    embedding_model,
    settings,
    qdrant_client,
    ollama_async_client,
)
import re
from app.utils.logger_config import logger
from app.utils.get_matching_reason import get_strengths_and_gaps

# Configuration
COLLECTION_NAME = settings.RESUMES_COLLECTION_NAME
INTERNSHIP_COLLECTION = settings.INTERNSHIPS_COLLECTION_NAME
VECTOR_SIZE = settings.VECTOR_SIZE
SIMILARITY_THRESHOLD = settings.RECOMMENDATION_SIMILARITY_THRESHOLD


async def recommend_jobs_combined(user_id: UUID, db: AsyncSession) -> dict[str, Any]:
    """
    Recommend both internal and external jobs by comparing the student's resume vector
    with Qdrant vectors using cosine similarity and payload rules.

    Args:
        user_id (UUID): The user's ID.
        db (AsyncSession): The async DB session.

    Returns:
        dict: {
            "user_id": str,
            "student_id": str,
            "screening_id": str | None,
            "matched_internal_jobs": List[str],
            "matched_external_jobs": List[str]
        }

    Raises:
        HTTPException: 404 if student not found, 500 on vector/store errors.
    """
    try:
        # Step 1: Get student by user_id
        student_result = await db.execute(
            select(Student).where(Student.user_id == user_id)
        )
        student = student_result.scalar_one_or_none()
        if not student:
            logger.warning(f"Student not found for user_id={user_id}")
            raise HTTPException(status_code=404, detail="Student not found")
        student_id = student.student_id
        logger.info(f"Found student_id={student_id} for user_id={user_id}")

        # Step 2: Fetch resume vector and payload from Qdrant
        try:
            qdrant_result = await qdrant_client.retrieve(
                collection_name=settings.RESUMES_COLLECTION_NAME,
                ids=[str(student_id)],
                with_vectors=True,
                with_payload=True,
            )
        except Exception as e:
            logger.exception(f"Failed to retrieve student vector from Qdrant: {str(e)}")
            raise HTTPException(status_code=500, detail="Vector retrieval failed")

        if not qdrant_result:
            logger.warning(f"No vector found in Qdrant for student_id={student_id}")
            return {
                "user_id": str(user_id),
                "student_id": str(student_id),
                "screening_id": None,
                "matched_internal_jobs": [],
                "matched_external_jobs": [],
            }

        student_vector = qdrant_result[0].vector
        student_payload = qdrant_result[0].payload.get("summary", {})
        resume_skills = student_payload.get("skills","")

        # Step 3: Concurrent external search + internal scroll
        logger.info("Starting Qdrant searches (external + internal) concurrently")

        external_task = qdrant_client.search(
            collection_name=settings.INTERNSHIPS_COLLECTION_NAME,
            query_vector=student_vector,
            limit=10000,
            with_payload=True,
            score_threshold=SIMILARITY_THRESHOLD,
        )
        internal_task = qdrant_client.scroll(
            collection_name=settings.JOB_COLLECTION_NAME,
            with_vectors=True,
            with_payload=True,
            limit=10000,
        )

        external_results, (internal_jobs, _) = await asyncio.gather(
            external_task, internal_task
        )
        logger.info(
            f"Fetched {len(external_results)} external and {len(internal_jobs)} internal jobs"
        )

        # Step 4: Match internal jobs by similarity + payload
        internal_matches = []
        for job in internal_jobs:
            try:
                similarity = util.cos_sim(student_vector, job.vector).item()
                if similarity >= SIMILARITY_THRESHOLD and check_payload_match(
                    job.payload.get("summary", {}), student_payload
                ):  
                    internal_matches.append((job.id, round(similarity * 100, 2)))
            except Exception as e:
                logger.warning(f"Skipping internal job {job.id} due to error: {e}")

        external_matches = [
            (res.id, round(res.score * 100, 2)) for res in external_results
        ]
        logger.info(
            f"Matched {len(internal_matches)} internal and {len(external_matches)} external jobs (pre-DB check)"
        )

        # Step 5: Concurrently fetch valid job_ids + screening + resume_version
        all_ids = {jid for jid, _ in internal_matches + external_matches}
        valid_jobs_task = db.execute(
            select(JobPosting.job_id).where(JobPosting.job_id.in_(all_ids))
        )
        screening_task = db.execute(
            select(ResumeScreeningResult)
            .where(ResumeScreeningResult.student_id == student_id)
            .order_by(ResumeScreeningResult.screened_at.desc())
        )
        resume_version_task = db.execute(
            select(ResumeVersion).where(ResumeVersion.student_id == student_id)
        )

        valid_job_ids_result, screening_result, version_result = await asyncio.gather(
            valid_jobs_task, screening_task, resume_version_task
        )
        valid_ids = {str(row[0]) for row in valid_job_ids_result.all()}

        internal_matches = [
            (jid, score) for jid, score in internal_matches if jid in valid_ids
        ]
        external_matches = [
            (jid, score) for jid, score in external_matches if jid in valid_ids
        ]

        screening = screening_result.scalar_one_or_none()
        version = version_result.scalars().first()

        if screening:
            screening_id = screening.screening_id
        else:
            screening_id = uuid4()
            version_id = version.version_id if version else uuid4()
            screening = ResumeScreeningResult(
                screening_id=screening_id,
                version_id=version_id,
                student_id=student_id,
                is_qualified=True,
            )
            db.add(screening)
            logger.info(
                f"Created new screening_id={screening_id} for student_id={student_id}"
            )

        # Step 6: Fetch existing internship_ids to avoid duplicates
        existing_links_result = await db.execute(
            select(ResumeScreeningInternship.internship_id).where(
                ResumeScreeningInternship.screening_id == screening_id
            )
        )
        existing_internship_ids = {str(row[0]) for row in existing_links_result.all()}

        # Step 7: Insert ResumeScreeningInternship (deduplicated)
        for job_id, score in external_matches:
            if job_id not in existing_internship_ids:
                job_point = next((j for j in external_results if j.id == job_id), None)
                if job_point:
                    job_summary = job_point.payload.get("summary", {})
                    job_skills = job_summary.get("skills", "")
                    matching_skills, missing_skills = get_strengths_and_gaps(resume_skills, job_skills)
                else:
                    matching_skills, missing_skills = [], []
                await db.merge(
                    ResumeScreeningInternship(
                        screening_id=screening_id,
                        internship_id=job_id,
                        matching_score=score,
                        matching_skills=matching_skills,
                        missing_skills=missing_skills,
                        source="External",
                    )
                )

        for job_id, score in internal_matches:
            if job_id not in existing_internship_ids:

                job_point = next((j for j in internal_jobs if j.id == job_id), None)
                if job_point:
                    job_summary = job_point.payload.get("summary", {})
                    job_skills = job_summary.get("skills", "")
                    matching_skills, missing_skills = get_strengths_and_gaps(resume_skills, job_skills)
                else:
                    matching_skills, missing_skills = [], []

                await db.merge(
                    ResumeScreeningInternship(
                        screening_id=screening_id,
                        internship_id=job_id,
                        matching_score=score,
                        matching_skills=matching_skills,
                        missing_skills=missing_skills,
                        source="Internal",
                    )
                )

                # Step 8: Insert into employer screening (deduplicated)
                try:
                    screening_obj = (
                        (
                            await db.execute(
                                select(JobCandidateScreening).where(
                                    JobCandidateScreening.job_id == job_id
                                )
                            )
                        )
                        .scalars()
                        .first()
                    )

                    if not screening_obj:
                        employer_id = (
                            await db.execute(
                                select(JobPosting.employer_id).where(
                                    JobPosting.job_id == job_id
                                )
                            )
                        ).scalar()
                        screening_obj = JobCandidateScreening(
                            screening_id=uuid4(), employer_id=employer_id, job_id=job_id
                        )
                        db.add(screening_obj)
                        await db.flush()

                    # Check existing JobCandidateMatching
                    existing_match = (
                        (
                            await db.execute(
                                select(JobCandidateMatching)
                                .where(
                                    JobCandidateMatching.screening_id
                                    == screening_obj.screening_id
                                )
                                .where(JobCandidateMatching.student_id == student_id)
                            )
                        )
                        .scalars()
                        .first()
                    )

                    if not existing_match and version:
                        await db.merge(
                            JobCandidateMatching(
                                screening_id=screening_obj.screening_id,
                                student_id=student_id,
                                version_id=version.version_id,
                                matching_score=score,
                                matching_skills=matching_skills,
                                missing_skills=missing_skills,
                                **extract_matching_fields(student_payload),
                            )
                        )
                except Exception as e:
                    logger.warning(
                        f"Skipping employer-side insert for job {job_id}: {e}"
                    )

        # Step 9: Final commit
        await db.commit()
        logger.info(
            f"Committed {len(external_matches)} external and {len(internal_matches)} internal matches "
            f"(deduplicated) for student_id={student_id}, screening_id={screening_id}"
        )

        return {
            "user_id": str(user_id),
            "student_id": str(student_id),
            "screening_id": str(screening_id),
            "matched_internal_jobs": [
                jid for jid, _ in internal_matches if jid not in existing_internship_ids
            ],
            "matched_external_jobs": [
                jid for jid, _ in external_matches if jid not in existing_internship_ids
            ],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            f"Unexpected error in recommend_jobs_combined for user_id={user_id}: {e}"
        )
        raise HTTPException(status_code=500, detail="Internal server error")


def check_payload_match(job_payload, candidate_payload):
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


async def batch_resume_internship_matching(db: AsyncSession):
    logger.info("Starting batch resume-internship matching process.")

    # Fetch all resumes from Qdrant
    all_resumes, _ = await qdrant_client.scroll(
        collection_name=COLLECTION_NAME,
        with_vectors=True,
        with_payload=True,
        limit=10000,
    )
    logger.info(f"Fetched {len(all_resumes)} resumes.")

    # Fetch all internships from Qdrant
    all_internships, _ = await qdrant_client.scroll(
        collection_name=INTERNSHIP_COLLECTION,
        with_vectors=True,
        with_payload=True,
        limit=10000,
    )
    logger.info(f"Fetched {len(all_internships)} internships.")

    for resume in all_resumes:
        student_id = resume.id
        if not student_id:
            logger.warning("Resume has no student_id. Skipping.")
            continue

        # Check resume version exists
        version_result = await db.execute(
            select(ResumeVersion).where(ResumeVersion.student_id == student_id)
        )
        version = version_result.scalars().first()
        if not version:
            logger.info(f"No ResumeVersion for student_id {student_id}. Skipping.")
            continue

        # Fetch or create ResumeScreeningResult
        screening_result = await db.execute(
            select(ResumeScreeningResult).where(
                ResumeScreeningResult.student_id == student_id
            )
        )
        screening = screening_result.scalars().first()
        if screening:
            screening_id = screening.screening_id
        else:
            screening_id = uuid4()
            screening = ResumeScreeningResult(
                screening_id=screening_id,
                version_id=version.version_id,
                student_id=student_id,
                is_qualified=True,
            )
            db.add(screening)
            await db.flush()
            logger.info(f"Created ResumeScreeningResult for student_id {student_id}")

        # Get existing matched internships
        existing_links = await db.execute(
            select(ResumeScreeningInternship.internship_id).where(
                ResumeScreeningInternship.screening_id == screening_id
            )
        )
        matched_internship_ids = {str(row[0]) for row in existing_links.all()}

        # Valid internships in JobPosting
        job_ids_result = await db.execute(select(JobPosting.job_id))
        valid_internship_ids = {str(row[0]) for row in job_ids_result.all()}

        resume_payload = resume.payload.get("summary", {})
        resume_skills = resume_payload.get("skills", "")

        for internship in all_internships:
            internship_id = internship.id

            if internship_id in matched_internship_ids:
                continue

            if internship_id not in valid_internship_ids:
                logger.warning(
                    f"Internship ID {internship_id} not in JobPosting. Skipping."
                )
                continue

            similarity = util.cos_sim(resume.vector, internship.vector).item()
            if similarity >= SIMILARITY_THRESHOLD:
                internship_payload = internship.payload.get("summary", {})
                internship_skills = internship_payload.get("skills", "")

                matching_skills, missing_skills = get_strengths_and_gaps(
                    resume_skills_str=resume_skills, job_skills_str=internship_skills
                )

                match = ResumeScreeningInternship(
                    screening_id=screening_id,
                    internship_id=internship_id,
                    matching_score=round(similarity * 100, 2),
                    matching_skills=matching_skills,
                    missing_skills=missing_skills,
                    source="External",
                )
                db.add(match)
                logger.info(
                    f"Matched student_id={student_id} to internship_id={internship_id} with score={similarity:.2f}"
                )

        await db.commit()
        logger.info(f"Committed matches for student_id={student_id}")

    logger.info("Batch resume-internship matching completed.")
    return {"status": "success"}

async def ensure_qdrant_collection():
    """Ensure Qdrant collection exists, create if not."""
    logger.info("Checking if Qdrant collection exists")

    try:
        collections = await qdrant_client.get_collections()
        existing_collections = [col.name for col in collections.collections]

        if COLLECTION_NAME not in existing_collections:
            logger.info(f"Creating new Qdrant collection: {COLLECTION_NAME}")
            await qdrant_client.recreate_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )
            logger.info(f"Successfully created collection: {COLLECTION_NAME}")
        else:
            logger.info(f"Collection {COLLECTION_NAME} already exists")

    except Exception as e:
        logger.error(f"Error ensuring Qdrant collection: {str(e)}")
        raise


async def get_student_by_user_id(db: AsyncSession, user_id: UUID):
    """Get student record by user_id."""
    logger.info(f"Fetching student for user_id: {user_id}")

    try:
        result = await db.execute(select(Student).filter(Student.user_id == user_id))
        student = result.scalars().first()
        logger.info(f"Student query result: {'Found' if student else 'Not found'}")
        return student

    except Exception as e:
        logger.error(f"Error fetching student: {str(e)}")
        raise


async def get_personal_info(db: AsyncSession, student_id):
    """Get personal info record by student_id."""
    logger.info(f"Fetching personal info for student_id: {student_id}")

    try:
        result = await db.execute(
            select(PersonalInfo).filter(PersonalInfo.student_id == student_id)
        )
        personal_info = result.scalars().first()
        logger.info(
            f"Personal info query result: {'Found' if personal_info else 'Not found'}"
        )
        return personal_info

    except Exception as e:
        logger.error(f"Error fetching personal info: {str(e)}")
        raise


async def get_skills(db: AsyncSession, user_profile_id):
    """Get all skills for user profile."""
    logger.info(f"Fetching skills for user_profile_id: {user_profile_id}")

    try:
        result = await db.execute(
            select(Skill).filter(Skill.user_id == user_profile_id)
        )
        skills = result.scalars().all()
        logger.info(f"Found {len(skills)} skills")
        return skills

    except Exception as e:
        logger.error(f"Error fetching skills: {str(e)}")
        raise


async def get_education(db: AsyncSession, user_profile_id):
    """Get all education records for user profile."""
    logger.info(f"Fetching education for user_profile_id: {user_profile_id}")

    try:
        result = await db.execute(
            select(Education).filter(Education.user_id == user_profile_id)
        )
        education = result.scalars().all()
        logger.info(f"Found {len(education)} education records")
        return education

    except Exception as e:
        logger.error(f"Error fetching education: {str(e)}")
        raise


def format_resume_data(skills, education, location: Optional[str]) -> str:
    """Format resume data into text string."""
    logger.info("Formatting resume data")

    skills_text = ", ".join([skill.skill_name for skill in skills])
    logger.info(f"Formatted skills: {skills_text}")

    qualifications = ", ".join(
        [
            f"{edu.degree or 'N/A'} in {edu.institution_name or 'N/A'} with grade {edu.grade} "
            f"started in {edu.start_date.year if edu.start_date else 'N/A'} "
            f"ending in {edu.end_date.year if edu.end_date else 'Present'}"
            for edu in education
        ]
    )
    logger.info(f"Formatted qualifications: {qualifications}")

    location_text = location or "Not mentioned"
    logger.info(f"Location: {location_text}")

    combined_data = f"Skills: {skills_text}\nQualifications: {qualifications}\nLocation: {location_text}"
    return combined_data


async def create_resume_vector(resume_data: str):
    """Create vector embedding from resume data."""
    logger.info("Creating vector embedding from resume data")

    try:
        # Extract skills for vectorization (assuming this is what you want)
        skills_match = re.search(r"Skills: (.+?)(?:\n|$)", resume_data)
        skills_text = skills_match.group(1) if skills_match else resume_data

        vector = embedding_model.encode(skills_text, normalize_embeddings=False)
        logger.info(f"Created vector with shape: {vector.shape}")
        return vector

    except Exception as e:
        logger.error(f"Error creating vector: {str(e)}")
        raise


def parse_llm_summary(summary: ResumeSummary) -> dict[str, Any]:
    """Post-process LLM summary for final adjustments like setting default year."""
    logger.info("Parsing validated ResumeSummary object")

    try:
        resume_data = summary.model_dump()

        # Ensure passed_out_year is a valid int (not None or str)
        if (
            resume_data.get("passed_out_year") is None
            or isinstance(resume_data.get("passed_out_year"), str)
        ):
            resume_data["passed_out_year"] = datetime.now().year
            logger.info(f"Set default passed_out_year to: {datetime.now().year}")

        return resume_data

    except Exception as e:
        logger.error(f"Error post-processing ResumeSummary: {str(e)}", exc_info=True)
        return {}


async def store_vector_point(student_id, vector, resume_data: dict[str, Any]):
    """Store vector point in Qdrant."""
    logger.info(f"Storing vector point for student_id: {student_id}")

    try:
        point = PointStruct(
            id=str(student_id),
            vector=vector.tolist(),
            payload={"student_id": str(student_id), "summary": resume_data},
        )

        logger.info(
            f"Resume Points to store: ID={point.id}, Payload keys: {list(point.payload.keys())}"
        )

        await qdrant_client.upsert(collection_name=COLLECTION_NAME, points=[point])
        logger.info(f"Successfully stored vector point for student_id: {student_id}")

    except Exception as e:
        logger.error(f"Error storing vector point: {str(e)}")
        raise


async def summarize_resume_with_llm(resume_text: str) -> ResumeSummary:
    """
    Asynchronously summarize resume text using LLM and return structured output.

    Args:
        resume_text: Raw resume text to summarize

    Returns:
        ResumeSummary: Structured summary validated by Pydantic
    """
    logger.info("Starting LLM resume summarization")
    logger.info(f"Input resume text length: {len(resume_text)} characters")

    sys_prompt = """
    You are an intelligent assistant that extracts structured, concise information from resumes to support job and internship matching.
    Given a resume, extract only the most relevant details and return them in the following structured JSON format. Ensure:
    - All text is in lowercase.
    - Convert any abbreviations to full forms (e.g., "mern" → "mongo, express, react, node").
    - Be concise and avoid generic or repetitive content.
    - For "degree_qualification", extract only the latest education degree name (e.g., bachelor of technology, bachelor of engineering).
    - "branch" refers to the field of study (e.g., computer science and engineering).
    - Use the latest education dates to fill "start_year" and "passed_out_year" (e.g., from "2021 - 2025" or "2021 - present").
    - "grade" must always be one float value from the latest education.
    - If a field is unknown, return it as empty or null.
    Expected format:
    {
        "skills": "",
        "degree_qualification": "",
        "college_name": "",
        "branch": "",
        "start_year": null,
        "passed_out_year": null,
        "location": "",
        "grade": null
    }
    """

    try:
        logger.info("Sending request to async Ollama client")

        response = await ollama_async_client.chat(
            model=settings.OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": resume_text}
            ],
            options={"temperature": 0.2},
            format=ResumeSummary.model_json_schema(),
        )

        content = response["message"]["content"].strip()
        logger.info(f"LLM response length: {len(content)} characters")

        try:
            summary = ResumeSummary.model_validate_json(content)
            logger.info("Successfully parsed structured resume summary")
            return summary
        except Exception as parse_err:
            logger.error(f"Failed to parse structured resume: {parse_err}")
            logger.debug(f"Raw LLM content: {content}")
            raise

    except Exception as e:
        logger.error(f"Error in LLM summarization: {str(e)}", exc_info=True)
        raise Exception(f"Failed to summarize resume with LLM: {str(e)}")


async def resume_vectorstore_v2(user_id: UUID, db: AsyncSession) -> dict[str, Any]:
    """
    Asynchronously process and store resume data in vector database.

    Args:
        user_id: UUID of the user
        db: Async database session

    Returns:
        Dict containing success message and summary or error information
    """
    logger.info(f"Starting resume vector store process for user_id: {user_id}")

    try:
        # Step 1: Ensure Qdrant collection exists
        await ensure_qdrant_collection()

        # Step 2: Get student record
        student = await get_student_by_user_id(db, user_id)
        if not student:
            logger.error(f"Student not found for user_id: {user_id}")
            return {"error": "Student not found"}

        logger.info(f"Found student with student_id: {student.student_id}")

        # Step 3: Get personal_info record
        personal_info = await get_personal_info(db, student.student_id)
        if not personal_info:
            logger.error(
                f"Personal info not found for student_id: {student.student_id}"
            )
            return {"error": "Personal info not found"}

        logger.info(f"Found personal info with profile_id: {personal_info.id}")

        # Step 4: Fetch skills and education concurrently
        skills, education = await asyncio.gather(
            get_skills(db, personal_info.id), get_education(db, personal_info.id)
        )

        logger.info(
            f"Retrieved {len(skills)} skills and {len(education)} education records"
        )

        # Step 5: Format resume data
        combined_resume_data = format_resume_data(
            skills, education, personal_info.location
        )
        logger.info(f"Combined DB Resume Data: {combined_resume_data}")

        # Step 6: Summarize with LLM and create vector
        summary, vector = await asyncio.gather(
            summarize_resume_with_llm(combined_resume_data),
            create_resume_vector(combined_resume_data),
        )

        logger.info(f"LLM Summary received: {summary}")

        # Step 7: Parse and validate summary
        resume_data = parse_llm_summary(summary)
        if not resume_data:
            logger.error("Failed to parse LLM summary into valid JSON")
            return {"error": "Failed to parse resume summary"}

        logger.info(f"Parsed JSON data: {resume_data}")

        # Step 8: Create and store vector point
        await store_vector_point(student.student_id, vector, resume_data)

        logger.info(
            f"Successfully stored resume vector for student_id: {student.student_id}"
        )

        return {
            "message": f"Resume data summarized and stored in vector DB for user_id={user_id}",
            "summary": resume_data,
        }

    except Exception as e:
        logger.error(
            f"Error in resume_vectorStore for user_id {user_id}: {str(e)}",
            exc_info=True,
        )
        return {"error": f"Internal server error: {str(e)}"}
