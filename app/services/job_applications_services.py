import uuid
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
import numpy as np
from sentence_transformers import util
from app.database.models.job_postings_models import JobPosting
from app.database.models.job_applications_models import JobApplication
from app.database.models.students_models import Student
from app.database.models.resume_versions_models import ResumeVersion
from app.schemas.job_applications_schema import JobApplicationCreate
from app.utils.logger_config import logger
from app.database.models.enums_models import JobApplicationStatus
from app.utils.settings import settings, qdrant_client


async def apply_for_job(
    resume_version_id: uuid.UUID,
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
):
    """
    Apply for a job using a selected resume version and calculate fitment score.

    This function performs the following steps:
    - Validates that the provided resume version, job posting, and student exist.
    - Retrieves vector representations of the resume and job from Qdrant.
    - Computes the cosine similarity between the two vectors to determine a fitment score.
    - Creates a new job application record in the database with the fitment score and initial status.

    Args:
        resume_version_id (uuid.UUID): ID of the resume version used for the application.
        job_id (uuid.UUID): ID of the job to apply for.
        user_id (uuid.UUID): ID of the user submitting the application.
        db (AsyncSession): SQLAlchemy asynchronous session for database access.

    Returns:
        JobApplication: The newly created job application object.

    Raises:
        HTTPException: If any of the resume, job, or student records are not found,
                       or if vector data is missing in Qdrant.
        HTTPException: 500 error if any unexpected exception occurs during application creation.
    """
    try:
        # Fetch resume
        resume_stmt = select(ResumeVersion).filter(
            ResumeVersion.version_id == resume_version_id
        )
        resume_result = await db.execute(resume_stmt)
        resume_version = resume_result.scalar_one_or_none()
        if not resume_version:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Resume version with ID {resume_version_id} not found",
            )

        # Fetch job posting
        job_stmt = select(JobPosting).filter(JobPosting.job_id == job_id)
        job_result = await db.execute(job_stmt)
        job_posting = job_result.scalar_one_or_none()
        if not job_posting:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job posting with ID {job_id} not found",
            )

        # Fetch student
        student_stmt = select(Student).filter(Student.user_id == user_id)
        student_result = await db.execute(student_stmt)
        student = student_result.scalar_one_or_none()
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Student profile not found for user ID {user_id}",
            )

        # Fetch vectors from Qdrant
        resume_vector_response = await qdrant_client.retrieve(
            collection_name=settings.RESUMES_COLLECTION_NAME,
            ids=[str(student.student_id)],
            with_vectors=True,
        )
        job_vector_response = await qdrant_client.retrieve(
            collection_name=settings.JOB_COLLECTION_NAME,
            ids=[str(job_id)],
            with_vectors=True,
        )

        if not resume_vector_response or not resume_vector_response[0].vector:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Resume vector not found for student_id {student.student_id}",
            )
        if not job_vector_response or not job_vector_response[0].vector:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job vector not found for job_id {job_id}",
            )

        # Compute fitment score
        resume_vector = np.array(resume_vector_response[0].vector)
        job_vector = np.array(job_vector_response[0].vector)

        similarity = util.cos_sim(resume_vector, job_vector).item()
        fitment_score = round(similarity * 100, 2)

        # Create job application record
        job_application_data = JobApplicationCreate(
            application_id=uuid.uuid4(),
            job_id=job_id,
            student_id=student.student_id,
            resume_version_id=resume_version_id,
            status=JobApplicationStatus.InProgress,
            current_stage="Application Submitted",
            fitment_score=fitment_score,
        )

        db_job_application = JobApplication(**job_application_data.dict())
        db.add(db_job_application)
        await db.commit()
        await db.refresh(db_job_application)

        logger.info(
            f"Created job application with ID: {db_job_application.application_id}"
        )
        return db_job_application

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating job application: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the job application",
        )


async def get_user_job_applications(
    user_id: uuid.UUID,
    db: AsyncSession,
):
    """
    Retrieve all job applications submitted by a student (identified via user_id),
    grouped by application status.

    This function:
    - Fetches the student profile using the given user_id.
    - Retrieves all job applications for that student along with job title and company name.
    - Groups the applications by their status (e.g., InProgress, Selected, Rejected).

    Args:
        user_id (uuid.UUID): The UUID of the user (student).
        db (AsyncSession): SQLAlchemy asynchronous session for database access.

    Returns:
        dict: A dictionary grouping job applications by status.

    Raises:
        HTTPException: 404 if student is not found.
        HTTPException: 500 for database or unexpected errors.
    """
    try:
        # Get student
        student_stmt = select(Student).filter(Student.user_id == user_id)
        student_result = await db.execute(student_stmt)
        student = student_result.scalar_one_or_none()
        if not student:
            raise HTTPException(
                status_code=404,
                detail="Student not found for given user_id",
            )

        # Get job applications joined with job posting
        stmt = (
            select(
                JobApplication.application_id,
                JobApplication.job_id,
                JobApplication.student_id,
                JobApplication.status,
                JobApplication.applied_on,
                JobApplication.current_stage,
                JobApplication.fitment_score,
                JobApplication.last_updated,
                JobPosting.title.label("job_title"),
                JobPosting.company_name.label("company_name"),
            )
            .join(JobPosting, JobPosting.job_id == JobApplication.job_id)
            .where(JobApplication.student_id == student.student_id)
        )

        result = await db.execute(stmt)
        applications = result.all()

        # Group applications by status
        grouped = {status.value: [] for status in JobApplicationStatus}
        for app in applications:
            app_status = (
                app.status.value if hasattr(app.status, "value") else app.status
            )
            grouped.setdefault(app_status, []).append(
                {
                    "application_id": app.application_id,
                    "job_id": app.job_id,
                    "status": app_status,
                    "applied_on": app.applied_on,
                    "current_stage": app.current_stage,
                    "fitment_score": app.fitment_score,
                    "last_updated": app.last_updated,
                    "job_title": app.job_title,
                    "company_name": app.company_name,
                }
            )

        return grouped

    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Database query failed")

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred")
