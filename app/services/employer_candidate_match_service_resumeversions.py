import logging
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams
from sentence_transformers import util
from sqlalchemy import desc, and_
from sqlalchemy.orm import Session
from typing import Optional, List
from app.database.db import get_db
from app.database.models import JobCandidateMatching, JobCandidateScreening, Student, ResumeScreeningInternship,ResumeScreeningResult,ResumeVersion
from app.database.models.job_postings_models import JobPosting
from app.services.user_service import get_structured_resume_data_withversion
from app.utils.settings import chat, embedding_model, settings
import re
import json
from app.utils.logger_config import logger


app = FastAPI()

# Configuration
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = settings.JOB_COLLECTION_NAME
RESUME_COLLECTION = settings.RESUMES_COLLECTION_NAME
VECTOR_SIZE = settings.VECTOR_SIZE # for all-MiniLM-L6-v2
SIMILARITY_THRESHOLD = settings.RECOMMENDATION_SIMILARITY_THRESHOLD

# Model and client

qdrant_client = QdrantClient(url=QDRANT_URL)


# Summarization prompt
def summarize_resume_with_llm(job_text: str) -> str:
    prompt = f"""
        You are an AI assistant that extracts only the most essential and structured information from job descriptions for the purpose of resume matching.
        Given the job description below, extract only the most relevant details and output a JSON in the format below. Ensure:
        - All text is in lowercase.
        - Convert any abbreviations or short forms to their full forms (e.g., "mern" → "mongo, express, react, node").
        - Be concise and avoid generic or repetitive content.
        - if any of the fields in the json are not found in the job description keep it empty, don't hallucinate to keep values
        - For "degree_qualification", keep only full forms (e.g: bachelor of technology,bachelor of engineering,bachelor of science) .
        - "branch" refers to the field of study, use the standard naming convention(e.g: computer science and engineering, electronics and communication engineering, information technology).
        Return the JSON in this format:
        json:{{
        "skills": "",
        "degree_qualification": "",
        "college_type": "",
        "branch": "",
        "passed_out_year": ,
        "location": "",
        "grade":
        }}
        Job Description:
        \"\"\"{job_text}\"\"\"
        """
    response = chat.invoke(prompt)
    return response.content.strip()


# Store resume vector
def job_vectorStore(job_id_to_fetch: UUID, db: Session):
    # Step 1: Ensure Qdrant collection exists
    if COLLECTION_NAME not in [
        col.name for col in qdrant_client.get_collections().collections
    ]:
        qdrant_client.recreate_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )

    job_posting = (
        db.query(JobPosting).filter(JobPosting.job_id == job_id_to_fetch).first()
    )

    # Storing details in variables if job_posting is found
    if job_posting:
        employer_id = job_posting.employer_id
        company_name = job_posting.company_name
        title = job_posting.title
        description = job_posting.description
        location = job_posting.location
        job_type = job_posting.job_type
        category = job_posting.category
        required_skills = job_posting.required_skills
        min_experience = job_posting.min_experience
        salary_range = job_posting.salary_range
        application_deadline = job_posting.application_deadline
        additional_info = job_posting.additional_info
        is_active = job_posting.is_active
        posted_at = job_posting.posted_at
    else:
        # Handle the case where no job posting is found
        employer_id = None
        company_name = None
        title = None
        description = None
        location = None
        job_type = None
        category = None
        required_skills = None
        min_experience = None
        salary_range = None
        application_deadline = None
        additional_info = None
        is_active = None
        posted_at = None

    # Step 5: Format the resume data
    skills_text = ", ".join([skill for skill in required_skills])
    # qualifications = ", ".join([
    #     f"{edu.degree or 'N/A'} in {edu.field_of_study or 'N/A'}" for edu in education
    # ])

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
    summary = summarize_resume_with_llm(combined_job_data)
    logger.info(f"LLM Summary for JD: {summary}")

    match = re.search(r'json\s*(\{.*?\})\s*', summary, re.DOTALL)
    if match:
        json_str = match.group(1)
        job_data = json.loads(json_str)
        logger.info(f"JSON data: {job_data}")
    else:
        logger.info("No valid JSON found.")

    vector = embedding_model.encode(job_data.get("skills"), normalize_embeddings=False)

    # Step 7: Create Qdrant point and upsert

    point = PointStruct(
        id=str(job_id_to_fetch),
        vector=vector.tolist(),
        payload={"Job_id": str(job_id_to_fetch), "summary": job_data},
    )
    logger.info(f"Job Point to store: {point}")

    qdrant_client.upsert(collection_name=COLLECTION_NAME, points=[point])

    return {
        "message": f"Job data summarised for the job_id: {job_id_to_fetch}",
        "summary": job_data,
    }


def recommend_candidates_withversions(job_id: UUID, db: Session):
    logger.info(f"Recommending candidates for job_id: {job_id}")

    # Step 2: Fetch Job_id vector from Qdrant
    try:
        retrieved = qdrant_client.retrieve(
            collection_name=COLLECTION_NAME, ids=[str(job_id)], with_vectors=True
        )
        if not retrieved:
            logger.warning(f"No vector found for job_id={job_id}")
            return {str(job_id): []}

        job_point = retrieved[0]
        job_vector = job_point.vector
        job_payload = job_point.payload.get('summary', {})
        logger.info(f"Retrieved vector & payload for job_id={job_id}")

    except Exception as e:
        logger.exception(f"Error while retrieving Job vector: {e}")
        return {"error": "Failed to retrieve Job vector"}

    # Step 3: Scroll all internship vectors
    try:
        all_candidates, _ = qdrant_client.scroll(
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
    matched_version_ids = []
    similarity_scores = []
    matching_details = []
    for candidate in all_candidates:
        version_id = candidate.id
        resume_version = db.query(ResumeVersion).filter(ResumeVersion.version_id == version_id).first()
        if not resume_version:
            logger.info(f"Version_id {version_id} not found in resume_versions table. Skipping candidate.")
            continue

        similarity = util.cos_sim(job_vector, candidate.vector).item()
        logger.info(f"Matching score: {similarity}")
        if similarity >= SIMILARITY_THRESHOLD:
            candidate_payload = candidate.payload.get('summary', {})
            if check_payload_match(job_payload, candidate_payload):
                matched_version_ids.append(version_id)
                logger.info(f"version_id: {version_id}")
                similarity_scores.append(round(similarity * 100, 2))
                candidate_fields = extract_matching_fields(candidate_payload)
                matching_details.append(candidate_fields)

    logger.info(f"Matched {len(matched_version_ids)} student resumes")

    try:
        screening_id = uuid4()
        job_posting = db.query(JobPosting).filter(JobPosting.job_id == job_id).first()
        if not job_posting:
            logger.warning(f"JobPosting not found for job_id={job_id}")
            return {"error": "JobPosting not found"}

        employer_id = job_posting.employer_id

        # Create screening record
        screening = JobCandidateScreening(
            screening_id=screening_id, employer_id=employer_id, job_id=job_id
        )
        db.add(screening)
        db.commit()
        logger.info(f"Screening result committed with ID: {screening_id}")

        # Create matching records
        for version_id, score, details in zip(matched_version_ids, similarity_scores, matching_details):
                # Get student_id from resume_versions table
                resume_version = db.query(ResumeVersion).filter(ResumeVersion.version_id == version_id).first()
                if not resume_version:
                    logger.warning(f"ResumeVersion not found for version_id {version_id} during matching insertion")
                    continue
                student_id = resume_version.student_id

                matching = JobCandidateMatching(
                    screening_id=screening_id,
                    student_id=student_id,
                    version_id=version_id,
                    matching_reason=None,
                    matching_score=score,
                    degree_qualification=details.get("degree_qualification"),
                    college_name=details.get("college_name"),
                    branch=details.get("branch"),
                    passed_out_year=details.get("passed_out_year"),
                    grade=details.get("grade"),
                    college_type=details.get("college_type"),
                    location=details.get("location")
                )
                db.add(matching)
            

                # Fetch ResumeScreeningResult for student
                resume_screening_result = db.query(ResumeScreeningResult).filter(
                    ResumeScreeningResult.version_id == version_id
                ).first()
                if not resume_screening_result:
                    logger.warning(f"No ResumeScreeningResult for student_id {student_id}")
                    continue

                # Insert into ResumeScreeningInternship
                new_entry = ResumeScreeningInternship(
                    screening_id=resume_screening_result.screening_id,
                    internship_id=job_id,
                    ats_score=score,
                    matching_reason=None,
                    source="Internal"
                )
                db.merge(new_entry)  # Use merge to avoid duplicate PK conflicts


        db.commit()
        logger.info(f"Matching Candidates committed with screening_id: {screening_id} and added this job to the candidate in internshiprecommnedation table")

    except Exception as e:
        db.rollback()
        logger.exception(f"Failed to store screening and matching records: {e}")
        return {"error": "Failed to store screening and matching records"}

    return {
        "Job_id": str(job_id),
        "screening_id": str(screening_id),
        "matched_resumes": [str(sid) for sid in matched_version_ids],
    }

def check_payload_match(job_payload, candidate_payload):
    logger.info(f"Job Payload: {job_payload}")
    logger.info(f"candidate Payload: {candidate_payload}")
    fields = ["college_type", "branch", "passed_out_year", "grade"]
    for field in fields:
        job_value = job_payload.get(field)
        candidate_value = candidate_payload.get(field)
        if job_value is None or job_value == '':
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
    "college_name"
]

def extract_matching_fields(payload):
    return {field: payload.get(field) for field in MATCH_FIELDS}


def get_matchedresumes_for_job_withversions(job_id: UUID, db: Session = Depends(get_db)):
    try:
        # 1. Fetch all screening entries for the given job_id
        screenings = (
            db.query(JobCandidateScreening)
            .filter(JobCandidateScreening.job_id == job_id)
            .all()
        )
        if not screenings:
            raise HTTPException(
                status_code=404, detail="No screenings found for this job"
            )

        result = []
        for screening in screenings:
            # 2. For each screening, fetch all matches (student_id & matching_score)
            matches = (
                db.query(JobCandidateMatching)
                .filter(JobCandidateMatching.screening_id == screening.screening_id)
                .order_by(desc(JobCandidateMatching.matching_score))
                .all()
            )

            for match in matches:
                try:
                    # 4. Get structured resume data using user_id
                    resume_data = get_structured_resume_data_withversion(match.student_id,match.version_id, db)
                    resume_data["matching_score"] = match.matching_score
                    result.append(resume_data)
                except HTTPException as e:
                    logger.warning(
                        f"Failed to get resume for user {match.student_id}: {e.detail}"
                    )
                    continue
                except Exception as e:
                    logger.error(f"Unexpected error for user {match.student_id}: {str(e)}")
                    continue

        return result

    except Exception as e:
        logger.error(f"Failed to process job_id {job_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail="An error occurred while processing the request"
        )


def get_filtered_matchedresumes_for_job_withversions(
    job_id: UUID,
    degree_qualification: Optional[str] = Query(None),
    branch: Optional[str] = Query(None),
    passed_out_year: Optional[int] = Query(None),
    grade: Optional[float] = Query(None),
    college_type: Optional[str] = Query(None),
    matching_score: Optional[float] = Query(None),
    db: Session = Depends(get_db)
):
    try:
        screenings = (
            db.query(JobCandidateScreening)
            .filter(JobCandidateScreening.job_id == job_id)
            .all()
        )
        if not screenings:
            raise HTTPException(
                status_code=404, detail="No screenings found for this job"
            )

        result = []

        for screening in screenings:
            # Build dynamic filters
            filters = [JobCandidateMatching.screening_id == screening.screening_id]
            
            if degree_qualification:
                filters.append(JobCandidateMatching.degree_qualification == degree_qualification)
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
            matches = (
                db.query(JobCandidateMatching)
                .filter(and_(*filters))
                .order_by(desc(JobCandidateMatching.matching_score))
                .all()
            )

            for match in matches:
                try:
                    resume_data = get_structured_resume_data_withversion(match.student_id,match.version_id, db)
                    resume_data["matching_score"] = match.matching_score
                    result.append(resume_data)
                except HTTPException as e:
                    logger.warning(
                        f"Failed to get resume for user {match.student_id}: {e.detail}"
                    )
                    continue
                except Exception as e:
                    logger.error(f"Unexpected error for user {match.student_id}: {str(e)}")
                    continue

        return result

    except Exception as e:
        logger.error(f"Failed to process job_id {job_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail="An error occurred while processing the request"
        )