from typing import List, Optional
from uuid import UUID
from app.schemas.job_applications_schema import JobApplicationRead
from app.services.job_applications_services import (
    apply_for_job,
    get_user_job_applications,
)
from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.db import get_db
from app.database.models.job_postings_models import JobPosting
from app.schemas.job_postings_schema import (
    JobDescriptionInput,
    JobDescriptionOutput,
    JobPostingCreate,
    JobPostingRead,
    JobPostingFilterRequest,
)
from app.services import job_postings_services as job_service, notification_service
from app.services.job_postings_llm_service import generate_job_description_endpoint
from app.services.job_postings_services import (
    create_job_posting,
    filter_job_postings_service,
)
from app.utils.logger_config import logger
from app.services.employer_job_applications_service import (
    get_student_applications,
    get_student_applications_count,
)

router = APIRouter(
    prefix="/api/jobs",
    tags=["Jobs"],
    responses={
        503: {"description": "Llama service unavailable or failed"},
        500: {"description": "Internal server error during generation"},
        404: {"description": "Not found"},
    },
)


@router.post(
    "/create-job-postings",
    response_model=JobPostingRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_new_job(
    job: JobPostingCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new job posting.

    This endpoint accepts a job posting request body and creates a new job in the database.
    It also triggers any necessary background tasks such as LLM enrichment or vector generation.

    Args:
        job (JobPostingCreate): The job posting details.
        background_tasks (BackgroundTasks): Background task handler.
        db (AsyncSession): Database session.

    Returns:
        JobPostingRead: The created job posting.

    Raises:
        HTTPException: 500 if job creation fails.
    """
    try:
        created_job = await create_job_posting(
            db=db, job=job, background_tasks=background_tasks
        )
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Unexpected error in create_new_job endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Unexpected error creating job posting."
        )
    return created_job


@router.get("/get-job-postings/{job_id}", response_model=JobPostingRead)
async def read_job_posting(job_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Retrieve a job posting by its ID.

    Args:
        job_id (UUID): Unique ID of the job posting.
        db (AsyncSession): Database session.

    Returns:
        JobPostingRead: The job posting details.

    Raises:
        HTTPException: 404 if job not found.
    """
    db_job = await job_service.get_job_posting_by_id(db=db, job_id=job_id)
    if not db_job:
        raise HTTPException(
            status_code=404, detail=f"Job posting with ID {job_id} not found"
        )
    return db_job


@router.post("/generate-job-description", response_model=JobDescriptionOutput)
async def generate_job_description(job_input: JobDescriptionInput = Body(...)):
    """
    Generate a job description using an LLM based on provided input.

    Args:
        job_input (JobDescriptionInput): Job title and other metadata.

    Returns:
        JobDescriptionOutput: AI-generated job description content.

    Raises:
        HTTPException: 500 on LLM failure.
    """
    try:
        return await generate_job_description_endpoint(job_input=job_input)
    except HTTPException as http_exc:
        logger.warning(f"LLM HTTPException: {http_exc.detail}")
        raise http_exc
    except Exception as e:
        logger.error(f"LLM Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="LLM generation failed")


@router.get(
    "/get-job-postings-by-employer/{user_id}", response_model=List[JobPostingRead]
)
async def read_job_postings_by_employer(
    user_id: UUID, db: AsyncSession = Depends(get_db)
):
    """
    Retrieve all job postings created by a specific employer.

    Args:
        user_id (UUID): Employer's user ID.
        db (AsyncSession): Database session.

    Returns:
        List[JobPostingRead]: List of job postings by the employer.

    Raises:
        HTTPException: 404 if no postings found.
        HTTPException: 500 on database error.
    """
    try:
        jobs = await job_service.get_job_postings_by_employer(db=db, user_id=user_id)
        if not jobs:
            raise HTTPException(status_code=404, detail="No job postings found")
        return jobs
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching job postings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error retrieving postings")


@router.get("/get-all-job-postings", response_model=List[JobPostingRead])
async def read_all_job_postings(
    user_id: Optional[UUID] = None, db: AsyncSession = Depends(get_db)
):
    """
    Retrieve all active job postings.

    Optionally, exclude postings the given user has already applied to.

    Args:
        user_id (Optional[UUID]): Student user ID to exclude applied jobs.
        db (AsyncSession): Database session.

    Returns:
        List[JobPostingRead]: List of available job postings.

    Raises:
        HTTPException: 500 on error.
    """
    try:
        jobs = await job_service.get_all_job_postings(db=db, user_id=user_id)
        return jobs
    except Exception as e:
        logger.error(f"Error fetching all postings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve postings")


@router.post("/filter", response_model=List[JobPostingRead])
async def filter_job_postings(
    request: JobPostingFilterRequest, db: AsyncSession = Depends(get_db)
):
    """
    Filter job postings based on various criteria such as:
    - Remote preference
    - Location
    - Job type
    - Category
    - Title

    Args:
        request (JobPostingFilterRequest): Filtering parameters.
        db (AsyncSession): Database session.

    Returns:
        List[JobPostingRead]: Filtered list of job postings.
    """
    logger.info(f"Filter request: {request}")
    return await filter_job_postings_service(request, db)


@router.get("/get-all-applications/{job_id}")
async def get_applications_for_job(job_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Retrieve all student applications submitted for a specific job.

    Args:
        job_id (UUID): Job ID to retrieve applications for.
        db (AsyncSession): Database session.

    Returns:
        List[JobApplication]: List of student applications.
    """
    return await get_student_applications(job_id=job_id, db=db)


@router.get("/get-all-applications-count/{job_id}")
async def get_applications_count_for_job(
    job_id: UUID, db: AsyncSession = Depends(get_db)
):
    """
    Get the total count of student applications submitted for a job.

    Args:
        job_id (UUID): Job ID.
        db (AsyncSession): Database session.

    Returns:
        dict: Total number of applications for the job.
    """
    return await get_student_applications_count(job_id=job_id, db=db)


@router.patch("/{job_id}/deactivate", response_model=dict)
async def deactivate_job(job_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Deactivate a job posting by setting its `is_active` field to False.

    Args:
        job_id (UUID): ID of the job to deactivate.
        db (AsyncSession): Database session.

    Returns:
        dict: Confirmation message.

    Raises:
        HTTPException: 404 if job is not found.
        HTTPException: 400 if job is already inactive.
        HTTPException: 500 on failure to update.
    """
    try:
        result = await db.execute(select(JobPosting).where(JobPosting.job_id == job_id))
        job = result.scalars().first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if not job.is_active:
            raise HTTPException(status_code=400, detail="Job already inactive")

        job.is_active = False
        await db.commit()
        return {"message": "Job deactivated successfully"}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deactivating job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to deactivate job")


@router.post(
    "/apply",
    response_model=JobApplicationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Apply for a Job",
    description="Submits a job application with resume and calculates fitment score using LLM.",
)
async def apply(
    resume_version_id: UUID = Body(...),
    job_id: UUID = Body(...),
    user_id: UUID = Body(...),
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None,
):
    """
    Endpoint to apply for a job by submitting a resume version.

    - **resume_version_id**: UUID of the resume version to submit.
    - **job_id**: UUID of the job posting to apply for.
    - **user_id**: UUID of the user (student) applying for the job.
    """
    try:
        application_result = await apply_for_job(
            resume_version_id=resume_version_id,
            job_id=job_id,
            user_id=user_id,
            db=db,
        )
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error in apply endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the job application",
        )

    try:
        background_tasks.add_task(
            notification_service.send_notification,
            db,
            str(user_id),
            notification_service.NotificationType.JOB_APPLICATION,
            application_id=str(application_result.application_id),
        )
    except Exception as e:
        logger.error(
            f"Failed to start job application notification task: {str(e)}",
            exc_info=True,
        )

    return application_result


@router.get(
    "/get-applied/{user_id}",
    summary="Get Job Applications by User ID",
    description="Retrieves all job applications for a user, grouped by application status.",
)
async def get_user_job_applications_endpoint(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Endpoint to retrieve all job applications for a user by their user ID.

    - **user_id**: UUID of the user (student) to retrieve job applications for.
    """
    try:
        return await get_user_job_applications(user_id=user_id, db=db)
    except Exception as e:
        logger.error(
            f"Error in get_user_job_applications endpoint: {str(e)}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving job applications",
        )
