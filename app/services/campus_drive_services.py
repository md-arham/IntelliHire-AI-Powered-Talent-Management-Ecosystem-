from sqlalchemy import desc, exists, literal, union_all, select
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import (
    CampusPlacementOfficer,
    CampusPlacement,
    JobPosting,
    JobApplication,
    EmployerProfile,
    Student,
    StudentBatch,
    RecommendedJob,
    User,
    JobCandidateScreening,
    JobCandidateMatching,
)
from app.database.models.enums_models import JobType
from app.services.employer_candidate_match_service import (
    job_vectorStore,
    recommend_candidates,
)
from app.services.user_service import get_structured_resume_data
from app.utils.logger_config import logger
from uuid import uuid4, UUID
from datetime import datetime
from fastapi import HTTPException, BackgroundTasks
from typing import List, Dict, Any, Optional
from app.utils.campusdrive_utils import link_company_to_drive_if_not_exists
from app.database.models.campusplacement_models import CampusDrive


async def initiate_campus_drive(
    db: AsyncSession,
    employer_id: UUID,
    job_id: UUID,
    drive_id: UUID,
    background_tasks=BackgroundTasks,
):
    """
    Allows an employer to post a job under an active campus drive.
    The job is cloned as a new job record and marked inactive by default until approved.
    A new CampusPlacement record is also created to track the placement context.

    Args:
        db (AsyncSession): Database session.
        employer_id (UUID): UUID of the employer posting the job.
        job_id (UUID): UUID of the original job being posted.
        drive_id (UUID): UUID of the target campus drive (must be active).
        background_tasks (BackgroundTasks): Optional FastAPI background task manager.

    Returns:
        dict: Metadata including new campus_placement_id and cloned_job_id.
    """
    drive = (
        (
            await db.execute(
                select(CampusDrive).filter_by(drive_id=drive_id, is_active=True)
            )
        )
        .scalars()
        .first()
    )

    if not drive or drive.end_date < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired campus drive")

    original_job = (
        (
            await db.execute(
                select(JobPosting).filter_by(job_id=job_id, employer_id=employer_id)
            )
        )
        .scalars()
        .first()
    )

    if not original_job:
        raise HTTPException(status_code=404, detail="Job not found or unauthorized.")

    employer = (
        (await db.execute(select(EmployerProfile).filter_by(employer_id=employer_id)))
        .scalars()
        .first()
    )

    if not employer or not employer.company_id:
        raise HTTPException(status_code=400, detail="Employer profile is incomplete")

    cloned_job = JobPosting(
        job_id=uuid4(),
        job_origin=original_job.job_origin,
        job_category_type=original_job.job_category_type,
        employer_id=employer_id,
        company_name=original_job.company_name,
        title=original_job.title,
        description=original_job.description,
        location=original_job.location,
        category=original_job.category,
        application_deadline=original_job.application_deadline,
        additional_info=original_job.additional_info,
        is_active=False,
        posted_at=datetime.utcnow(),
        job_type="Campus_Driven",
        required_skills=original_job.required_skills,
        min_experience=original_job.min_experience,
        salary_range=original_job.salary_range,
        internship_type=original_job.internship_type,
        stipend=original_job.stipend,
        role=original_job.role,
        responsibilities=original_job.responsibilities,
        requirements=original_job.requirements,
    )
    db.add(cloned_job)
    await db.flush()

    try:
        background_tasks.add_task(job_vectorStore, cloned_job.job_id, db)
    except Exception as e:
        logger.error(f"Failed to start background task: {str(e)}")

    campus_placement = CampusPlacement(
        placement_id=uuid4(),
        drive_id=drive_id,
        company_id=employer.company_id,
        college_id=drive.college_id,
        job_id=cloned_job.job_id,
        drive_date=datetime.utcnow(),
        is_active=False,
        created_at=datetime.utcnow(),
    )
    db.add(campus_placement)
    await link_company_to_drive_if_not_exists(db, employer.company_id, drive_id)

    await db.commit()

    return {
        "campus_placement_id": campus_placement.placement_id,
        "cloned_job_id": cloned_job.job_id,
        "message": "Job successfully added under campus drive",
        "created_at": campus_placement.created_at,
    }


async def get_pending_jobs_for_college(db: AsyncSession, college_id: UUID):
    """
    Retrieves campus jobs that are pending approval for a specific college.

    Args:
        db (AsyncSession): The async DB session.
        college_id (UUID): College ID.

    Returns:
        List[CampusPlacement]: List of pending placements under drives for that college.
    """
    result = await db.execute(
        select(CampusPlacement)
        .filter_by(college_id=college_id, is_active=False)
        .options(
            joinedload(CampusPlacement.drive),
            joinedload(CampusPlacement.job),
        )
    )
    return result.scalars().all()


async def initate_campus_drive_by_campusofficer(
    db: AsyncSession,
    officer_id: UUID,
    drive_name: str,
    start_date: datetime,
    end_date: datetime,
    batch_id: UUID,
    min_cgpa: Optional[int] = None,
    max_backlogs: Optional[int] = None,
):
    """
    Allows a campus placement officer to create and register a new campus drive
    for their college, targeting a specific student batch with optional eligibility filters.

    Args:
        db (AsyncSession): Database session.
        officer_id (UUID): UUID of the campus placement officer initiating the drive.
        drive_name (str): Name of the campus drive.
        start_date (datetime): Start date of the drive.
        end_date (datetime): End date of the drive.
        batch_id (UUID): UUID of the target student batch.
        min_cgpa (Optional[int], optional): Minimum CGPA required for eligibility.
        max_backlogs (Optional[int], optional): Maximum number of backlogs allowed.

    Returns:
        dict: Contains metadata of the created drive including batch info.
    """
    officer = (
        (
            await db.execute(
                select(CampusPlacementOfficer).filter_by(officer_id=officer_id)
            )
        )
        .scalars()
        .first()
    )

    if not officer:
        raise HTTPException(status_code=404, detail="Invalid Campus Placement Officer")

    batch = (
        (await db.execute(select(StudentBatch).filter_by(batch_id=batch_id)))
        .scalars()
        .first()
    )

    if not batch or batch.college_id != officer.college_id:
        raise HTTPException(status_code=400, detail="Invalid or unauthorized batch")

    new_drive = CampusDrive(
        drive_id=uuid4(),
        college_id=officer.college_id,
        created_by_officer_id=officer_id,
        drive_name=drive_name,
        start_date=start_date,
        end_date=end_date,
        target_batch_id=batch_id,
        min_cgpa=min_cgpa,
        max_backlogs=max_backlogs,
        is_active=True,
        created_at=datetime.utcnow(),
    )

    db.add(new_drive)
    await db.commit()

    return {
        "drive_id": new_drive.drive_id,
        "message": "Campus drive created successfully",
        "start_date": new_drive.start_date,
        "end_date": new_drive.end_date,
        "target_batch": {
            "batch_year": batch.batch_year,
            "department": batch.department,
        },
    }


async def approve_campus_drive_job(
    db: AsyncSession,
    placement_id: UUID,
    college_id: UUID,
    background_tasks=BackgroundTasks,
):
    """
    Approves a campus job posted by an employer under a campus drive.
    Once approved:
        - The cloned job and placement are marked active.
        - Eligible students from the drive's target batch are fetched.
        - Recommendations are created for each student for the job.
        - A background task is triggered to update vector store for search relevance.

    Args:
        db (AsyncSession): Database session.
        placement_id (UUID): UUID of the CampusPlacement to approve.
        college_id (UUID): UUID of the college (validated against placement).
        background_tasks (BackgroundTasks): Optional FastAPI background task manager.

    Returns:
        dict: Success message including batch year and department.
    """
    placement = (
        (
            await db.execute(
                select(CampusPlacement)
                .filter_by(
                    placement_id=placement_id, college_id=college_id, is_active=False
                )
                .options(
                    joinedload(CampusPlacement.job), joinedload(CampusPlacement.drive)
                )
            )
        )
        .scalars()
        .first()
    )

    if not placement:
        raise HTTPException(status_code=404, detail="Campus Placement not found")

    placement.is_active = True
    placement.job.is_active = True

    batch_id = placement.drive.target_batch_id

    batch = (
        (
            await db.execute(
                select(StudentBatch).filter_by(batch_id=batch_id, college_id=college_id)
            )
        )
        .scalars()
        .first()
    )

    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found for the drive")

    student_ids = (
        (await db.execute(select(Student.student_id).filter_by(batch_id=batch_id)))
        .scalars()
        .all()
    )

    if not student_ids:
        raise HTTPException(status_code=404, detail="No students found in this batch.")

    try:
        background_tasks.add_task(recommend_candidates, placement.job_id, db)
    except Exception as e:
        logger.error(f"Failed to start background task: {str(e)}")

    db.add_all(
        [RecommendedJob(job_id=placement.job_id, student_id=sid) for sid in student_ids]
    )

    await db.commit()

    return {
        "message": f"Campus job approved and recommended to batch {batch.batch_year} ({batch.department})"
    }


async def get_student_campus_jobs(db: AsyncSession, student_id: UUID):
    """
    Returns all campus-driven jobs recommended to a student.

    Args:
        db (AsyncSession): Async DB session.
        student_id (UUID): Student's UUID.

    Returns:
        List[JobPosting]: List of jobs.
    """
    result = await db.execute(
        select(JobPosting)
        .join(RecommendedJob, RecommendedJob.job_id == JobPosting.job_id)
        .filter(
            RecommendedJob.student_id == student_id,
            JobPosting.job_type == JobType.Campus_Driven,
        )
    )
    return result.scalars().all()


async def get_cumulative_applicants(
    user_id: UUID, db: AsyncSession
) -> List[Dict[str, Any]]:
    """
    Retrieves all applicants (campus + recommended) under a placement officer's college.

    Args:
        user_id (UUID): Officer's user ID.
        db (AsyncSession): Async DB session.

    Returns:
        List[Dict[str, Any]]: Applicant data.
    """
    try:
        officer = (
            (
                await db.execute(
                    select(CampusPlacementOfficer).filter_by(user_id=user_id)
                )
            )
            .scalars()
            .first()
        )

        if not officer:
            raise HTTPException(status_code=404, detail="Officer not found")

        college_id = officer.college_id

        campus_applications = (
            select(
                Student.student_id,
                User.full_name.label("student_name"),
                StudentBatch.batch_year.label("batch"),
                JobApplication.status,
                JobPosting.title.label("job_title"),
                JobApplication.job_id,
                literal("campus").label("application_source"),
            )
            .select_from(Student)
            .join(User)
            .join(JobApplication)
            .join(JobPosting)
            .outerjoin(StudentBatch)
            .filter(
                Student.college_id == college_id,
                exists()
                .where(CampusPlacement.job_id == JobApplication.job_id)
                .where(CampusPlacement.college_id == college_id),
            )
        )

        recommended_applications = (
            select(
                Student.student_id,
                User.full_name.label("student_name"),
                StudentBatch.batch_year.label("batch"),
                JobApplication.status,
                JobPosting.title.label("job_title"),
                JobApplication.job_id,
                literal("recommended").label("application_source"),
            )
            .select_from(Student)
            .join(User)
            .join(JobApplication)
            .join(JobPosting)
            .outerjoin(StudentBatch)
            .filter(
                Student.college_id == college_id,
                exists()
                .where(RecommendedJob.job_id == JobApplication.job_id)
                .where(RecommendedJob.student_id == Student.student_id),
            )
        )

        combined_query = union_all(campus_applications, recommended_applications)
        result = await db.execute(combined_query)
        return [dict(row) for row in result.mappings().all()]

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(status_code=500, detail="Database error occurred")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Unexpected error occurred")


async def get_applicants_for_job(user_id: UUID, job_id: UUID, db: AsyncSession):
    """
    Returns all applicants for a job under a placement officer's college.

    Args:
        user_id (UUID): Campus officer's user ID.
        job_id (UUID): Target job.
        db (AsyncSession): Async DB session.

    Returns:
        List[Dict[str, Any]]: Applicant information.
    """
    try:
        officer = (
            (
                await db.execute(
                    select(CampusPlacementOfficer).filter_by(user_id=user_id)
                )
            )
            .scalars()
            .first()
        )
        if not officer:
            raise ValueError("Invalid Campus Placement Officer user_id")

        college_id = officer.college_id

        job_exists = (
            await db.execute(
                select(
                    exists().where(
                        CampusPlacement.job_id == job_id,
                        CampusPlacement.college_id == college_id,
                    )
                )
            )
        ).scalar()

        if not job_exists:
            raise ValueError("Job not found for this college")

        query = (
            select(
                Student.student_id,
                User.full_name.label("student_name"),
                StudentBatch.batch_year.label("batch"),
                JobApplication.status,
                JobPosting.title.label("job_title"),
                JobApplication.job_id,
                literal("campus").label("application_source"),
            )
            .select_from(Student)
            .join(User)
            .join(JobApplication)
            .join(JobPosting)
            .outerjoin(StudentBatch)
            .filter(
                Student.college_id == college_id,
                JobApplication.job_id == job_id,
            )
        )

        result = await db.execute(query)
        return [dict(row) for row in result.mappings().all()]

    except SQLAlchemyError as e:
        logger.exception("DB error")
        raise RuntimeError("Internal server error") from e
    except Exception as e:
        logger.exception(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred")


async def get_placement_matched_students(
    job_id: UUID, college_id: UUID, db: AsyncSession
):
    """
    Retrieves matched students with >60 score for a job from a specific college.

    Args:
        job_id (UUID): Job ID.
        college_id (UUID): College ID.
        db (AsyncSession): Async DB session.

    Returns:
        List[Dict[str, Any]]: Structured resumes with match scores.
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
            match_result = await db.execute(
                select(JobCandidateMatching)
                .where(
                    JobCandidateMatching.screening_id == screening.screening_id,
                    JobCandidateMatching.matching_score > 60,
                )
                .order_by(desc(JobCandidateMatching.matching_score))
            )
            matches = match_result.scalars().all()

            for match in matches:
                student_result = await db.execute(
                    select(Student).where(
                        Student.student_id == match.student_id,
                        Student.college_id == college_id,
                    )
                )
                student = student_result.scalars().first()

                if not student:
                    logger.warning(
                        f"Student not found for student_id {match.student_id} and college_id {college_id}"
                    )
                    continue

                user_id = student.user_id

                try:
                    resume_data = await get_structured_resume_data(user_id, db)
                    resume_data["matching_score"] = match.matching_score
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
