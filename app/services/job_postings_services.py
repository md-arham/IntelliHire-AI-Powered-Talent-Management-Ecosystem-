from math import ceil
from typing import List
import uuid
from app.schemas.internships_schema import InternshipFilterRequest
from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_
from app.database.models.employer_profiles_models import EmployerProfile
from app.database.models.bookmark_models import Bookmark
from app.database.models.students_models import Student
from app.database.models.job_applications_models import JobApplication
from app.database.models.job_postings_models import JobOriginType, JobPosting
from app.database.models.enums_models import InternshipType, JobType
from app.schemas.job_postings_schema import JobPostingCreate, JobPostingFilterRequest, JobPostingRead, PaginatedInternshipResponse
from app.services.employer_candidate_match_service import (
    job_vectorStore,
    recommend_candidates,
)
from app.services.employer_resume_extractor_service import match_resumes_to_job
from app.utils.logger_config import logger
from sqlalchemy import desc, func, select

async def create_job_posting(
    db: AsyncSession, job: JobPostingCreate, background_tasks: BackgroundTasks
) -> JobPosting:
    """
    Creates a new job posting in the database.
    Maps the provided user_id to the employer_id from employer_profiles table.

    Args:
        db (AsyncSession): The asynchronous database session.
        job (JobPostingCreate): The job posting data.
        background_tasks (BackgroundTasks): Background task manager.

    Returns:
        JobPosting: The created job posting record.

    Raises:
        HTTPException: If employer profile is not found or job_type is invalid.
    """
    logger.info("Attempting to create job posting")

    result = await db.execute(
        select(EmployerProfile).filter(EmployerProfile.user_id == job.employer_id)
    )
    employer_profile = result.scalar_one_or_none()

    if not employer_profile:
        logger.error("Employer profile not found for user ID: %s", job.employer_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employer profile not found for the provided user ID.",
        )

    job_data = job.model_dump()
    job_data["employer_id"] = employer_profile.employer_id
    job_id = uuid.uuid4()
    job_data["job_id"] = job_id

    if "job_type" in job_data and job_data["job_type"]:
        try:
            job_data["job_type"] = JobType(job_data["job_type"])
        except ValueError:
            logger.error("Invalid job_type: %s", job_data["job_type"])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid job_type value: {job_data['job_type']}",
            )
    if "internship_type" in job_data and job_data["internship_type"]:
        try:
            job_data["internship_type"] = InternshipType(job_data["internship_type"])
        except ValueError:
            logger.error("Invalid internship_type: %s", job_data["internship_type"])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid internship_type value: {job_data['internship_type']}",
            )

    db_job = JobPosting(**job_data)

    try:
        db.add(db_job)
        await db.commit()
        await db.refresh(db_job)
        logger.info(f"Created JobPosting with job_id: {db_job.job_id}")

        try:
            background_tasks.add_task(job_vectorStore, job_id, db)
            background_tasks.add_task(recommend_candidates, job_id, db)
            background_tasks.add_task(match_resumes_to_job, db, job_id)
        except Exception as e:
            logger.error(f"Failed to start background tasks: {str(e)}")

        return db_job

    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating job posting: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create job posting due to a server error.",
        )


async def get_job_posting_by_id(
    db: AsyncSession, job_id: uuid.UUID
) -> JobPosting | None:
    """
    Retrieves a single job posting by its UUID.

    Args:
        db (AsyncSession): The asynchronous database session.
        job_id (UUID): The ID of the job posting.

    Returns:
        JobPosting | None: The job posting if found, otherwise None.
    """
    result = await db.execute(select(JobPosting).filter(JobPosting.job_id == job_id))
    return result.scalar_one_or_none()


async def get_job_postings_by_employer(
    db: AsyncSession, user_id: uuid.UUID
) -> list[JobPosting]:
    """
    Retrieves all job postings for a given employer by user ID.

    Args:
        db (AsyncSession): The asynchronous database session.
        user_id (UUID): The user ID of the employer.

    Returns:
        list[JobPosting]: A list of job postings.

    Raises:
        HTTPException: If the employer profile is not found.
    """
    result = await db.execute(
        select(EmployerProfile).filter(EmployerProfile.user_id == user_id)
    )
    employer_profile = result.scalar_one_or_none()

    if not employer_profile:
        logger.error("Employer profile not found for user ID: %s", user_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employer profile not found for the provided user ID.",
        )

    result = await db.execute(
        select(JobPosting).filter(
            JobPosting.employer_id == employer_profile.employer_id
        )
    )
    return result.scalars().all()


async def get_all_job_postings(
    db: AsyncSession, user_id: uuid.UUID | None = None
) -> list[JobPosting]:
    """
    Retrieves all active job postings, optionally excluding those applied by a student.
    Annotates each job with bookmark status if user_id is provided.

    Args:
        db (AsyncSession): The async database session.
        user_id (UUID, optional): Student's user ID to personalize results.

    Returns:
        list[JobPosting]: List of job postings with isSaved and bookmark_id annotations.
    """
    query = select(JobPosting).filter(
        JobPosting.is_active,
        JobPosting.job_origin == JobOriginType.INTERNAL,
    )

    student_id = None
    if user_id:
        student_result = await db.execute(
            select(Student).filter(Student.user_id == user_id)
        )
        student = student_result.scalar_one_or_none()

        if not student:
            logger.warning("No student found for user_id: %s", user_id)
            # Continue without student-specific filtering instead of returning None
        else:
            student_id = student.student_id

            applied_jobs_subquery = (
                select(JobApplication.job_id)
                .filter(JobApplication.student_id == student_id)
                .subquery()
            )
            query = query.filter(JobPosting.job_id.not_in(applied_jobs_subquery))

    result = await db.execute(query)
    jobs = result.scalars().all()

    if student_id:
        bookmarks_result = await db.execute(
            select(Bookmark).filter(Bookmark.student_id == student_id)
        )
        bookmarks = bookmarks_result.scalars().all()
        bookmark_map = {bm.job_id: bm.bookmark_id for bm in bookmarks}

        for job in jobs:
            job.isSaved = job.job_id in bookmark_map
            job.bookmark_id = bookmark_map.get(job.job_id)
    else:
        for job in jobs:
            job.isSaved = False
            job.bookmark_id = None

    return jobs


async def filter_job_postings_service(
    request: JobPostingFilterRequest, db: AsyncSession
) -> List[JobPostingRead]:
    """
    Retrieve a filtered list of internal job postings that the student has not already applied to.

    This service:
    - Validates the student using the provided `user_id`.
    - Filters active internal job postings that the student has not already applied to.
    - Applies additional filters like remote preference, location, job type, category, and title.

    Args:
        request (JobPostingFilterRequest): Filter criteria including user_id, location, job type, etc.
        db (AsyncSession): SQLAlchemy asynchronous session for DB access.

    Returns:
        List[JobPostingRead]: A list of job postings matching the filters and eligibility.

    Raises:
        HTTPException: 404 if student is not found.
        HTTPException: 500 on unexpected errors or DB query failures.
    """
    try:
        student_query = await db.execute(
            select(Student).filter(Student.user_id == request.user_id)
        )
        student = student_query.scalars().first()
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")
        query = select(JobPosting).filter(
            JobPosting.is_active,
            JobPosting.job_origin == JobOriginType.INTERNAL,
        )

        applied_subquery = (
            select(JobApplication.job_id)
            .filter(JobApplication.student_id == student.student_id)
            .subquery()
        )
        query = query.filter(~JobPosting.job_id.in_(applied_subquery))

        if request.is_remote is not None:
            if request.is_remote:
                query = query.filter(JobPosting.location.ilike("%Remote%"))
            else:
                query = query.filter(
                    or_(
                        JobPosting.location.notilike("%Remote%"),
                        JobPosting.location.is_(None),
                    )
                )
        if request.location:
            query = query.filter(JobPosting.location.ilike(f"%{request.location}%"))
        if request.job_type:
            query = query.filter(JobPosting.job_type.ilike(f"%{request.job_type}%"))
        if request.category:
            query = query.filter(JobPosting.category.ilike(f"%{request.category}%"))
        if request.title:
            query = query.filter(JobPosting.title.ilike(f"%{request.title}%"))

        results = await db.execute(query)
        jobs = results.scalars().all()

        logger.info(f"Filtered {len(jobs)} job postings")
        return jobs

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error filtering postings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error filtering job postings")
        

async def get_paginated_internal_internships(
    request: InternshipFilterRequest,
    db: AsyncSession
) -> PaginatedInternshipResponse:
    """
    Retrieve a paginated and filtered list of internal internship job postings
    that the student has not already applied to.

    This service:
    - Validates the student using `user_id`.
    - Filters based on job origin and job category type.
    - Applies optional filters: remote preference, location, job type, category, and title.
    - Supports pagination and ordering by fetched timestamp.

    Args:
        request (InternshipFilterRequest): The internship filter criteria including user_id,
                                           location, job type, etc., along with pagination details.
        db (AsyncSession): SQLAlchemy asynchronous session for DB access.

    Returns:
        PaginatedInternshipResponse: A paginated response containing filtered internship postings.

    Raises:
        HTTPException: 404 if student is not found.
        HTTPException: 500 on DB errors or unexpected failures.
    """
    try:
        student_query = await db.execute(
            select(Student).filter(Student.user_id == request.user_id)
        )
        student = student_query.scalars().first()
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        query = select(JobPosting).filter(
            JobPosting.is_active.is_(True),
            JobPosting.job_origin == request.job_origin,
            JobPosting.job_category_type == request.job_category_type,
        )

        applied_subquery = (
            select(JobApplication.job_id)
            .filter(JobApplication.student_id == student.student_id)
            .subquery()
        )
        query = query.filter(~JobPosting.job_id.in_(applied_subquery))

        if request.work_type:
                try:
                    work_type = InternshipType[request.work_type]
                    query = query.filter(JobPosting.internship_type == work_type)
                except KeyError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid `type` value: {request.type}"
                    )
        # if request.job_type:
        #     query = query.filter(JobPosting.job_type.ilike(f"%{request.job_type}%"))
        if request.job_type:
                try:
                    job_type = JobType[request.job_type]
                    query = query.filter(JobPosting.job_type == job_type)
                except KeyError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid `job_type` value: {request.job_type}"
                    )
                
        if request.location:
            query = query.filter(JobPosting.location.ilike(f"%{request.location}%"))

        if request.category:
            query = query.filter(JobPosting.category.ilike(f"%{request.category}%"))

        if request.role:
            query = query.filter(JobPosting.role == request.role.strip())

        if request.title:
            query = query.filter(JobPosting.title.ilike(f"%{request.title}%"))

        # Pagination setup
        page = max(1, getattr(request, "page", 1))
        page_size = getattr(request, "page_size", 10)
        offset = (page - 1) * page_size

        # Count total
        total_stmt = query.with_only_columns(func.count()).order_by(None)
        total_result = await db.execute(total_stmt)
        total = total_result.scalar()

        # Apply limit and offset
        paginated_query = (
            query.offset(offset).limit(page_size).order_by(desc(JobPosting.fetched_at))
        )
        results = await db.execute(paginated_query)
        jobs = results.scalars().all()

        if student.student_id:
            bookmarks_result = await db.execute(
                select(Bookmark).filter(Bookmark.student_id == student.student_id)
            )
            bookmarks = bookmarks_result.scalars().all()
            bookmark_map = {bm.job_id: bm.bookmark_id for bm in bookmarks}

            for job in jobs:
                job.isSaved = job.job_id in bookmark_map
                job.bookmark_id = bookmark_map.get(job.job_id)
                job.additional_info.update({
                    "job_origin": job.job_origin.value,
                    "job_category_type": job.job_category_type.value
                })
        else:
            for job in jobs:
                job.isSaved = False
                job.bookmark_id = None


        logger.info(f"Filtered {len(jobs)} job postings")

        return PaginatedInternshipResponse(
            items=jobs,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=ceil(total / page_size) if page_size else 0,
            has_more=(offset + page_size) < total,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error filtering postings: {e}")
        raise HTTPException(status_code=500, detail="Error fetching and filtering job postings")
