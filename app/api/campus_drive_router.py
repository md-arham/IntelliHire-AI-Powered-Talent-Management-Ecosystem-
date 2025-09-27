from fastapi import APIRouter, Depends, status, BackgroundTasks, HTTPException
from fastapi.params import Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from uuid import UUID

from app.database.db import get_db
from app.database.models import (
    EmployerProfile,
    CampusPlacementOfficer,
    Student,
    CampusPlacement,
)
from app.schemas.campus_drive_schemas import (
    CampusDriveInitiateRequest,
    CampusDriveInitiateResponse,
    CampusDriveJobOut,
    CampusDriveApprovalRequest,
    CampusJobStudentViewOut,
    CampusDriveCreateRequest,
    CampusDriveCreateResponse,
)
from app.services.campus_drive_services import (
    initiate_campus_drive,
    get_pending_jobs_for_college,
    approve_campus_drive_job,
    get_student_campus_jobs,
    get_cumulative_applicants,
    get_applicants_for_job,
    get_placement_matched_students,
    initate_campus_drive_by_campusofficer,
)
from app.utils.logger_config import logger

router = APIRouter(prefix="/api/campus-drive", tags=["Campus Drive"])


@router.post(
    "/initiate",
    response_model=CampusDriveInitiateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def initiate_campus_drive_api(
    request: CampusDriveInitiateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Employer links a job to an existing campus drive.

    - Validates employer by user ID.
    - Associates a cloned job with the specified drive.
    - Adds job under company & drive context.

    Returns:
        CampusDriveInitiateResponse with job & placement info.
    """
    try:
        result = await db.execute(
            select(EmployerProfile).filter_by(user_id=request.employer_user_id)
        )
        employer = result.scalars().first()
        if not employer:
            raise HTTPException(status_code=404, detail="Employer not found")

        return await initiate_campus_drive(
            db=db,
            employer_id=employer.employer_id,
            job_id=request.job_id,
            drive_id=request.drive_id,  # changed from college_id
            background_tasks=background_tasks,
        )
    except Exception as e:
        logger.error(f"Failed to initiate campus drive: {e}")
        raise HTTPException(status_code=500, detail="Failed to initiate campus drive")


@router.post(
    "/create-drive",
    response_model=CampusDriveCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_campus_drive_api(
    request: CampusDriveCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Campus Placement Officer initiates a new campus drive.

    - Requires officer user ID and batch_id (target).
    - Must belong to a valid college & batch combo.
    - Stores eligibility criteria and time window.

    Returns:
        CampusDriveCreateResponse with new drive metadata.
    """
    try:
        result = await db.execute(
            select(CampusPlacementOfficer).filter_by(user_id=request.officer_user_id)
        )
        officer = result.scalars().first()
        if not officer:
            raise HTTPException(status_code=404, detail="Placement officer not found")

        return await initate_campus_drive_by_campusofficer(
            db=db,
            officer_id=officer.officer_id,
            drive_name=request.drive_name,
            start_date=request.start_date,
            end_date=request.end_date,
            batch_id=request.target_batch_id,
            min_cgpa=request.min_cgpa,
            max_backlogs=request.max_backlogs,
        )
    except Exception as e:
        logger.error(f"Failed to create campus drive: {e}")
        raise HTTPException(status_code=500, detail="Failed to create campus drive")


@router.get("/pending", response_model=List[CampusDriveJobOut])
async def get_pending_campus_jobs(
    current_user_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Fetches all campus drive jobs that are pending approval for a given officer.

    - The user must be a valid Campus Placement Officer.
    - Returns a list of jobs initiated for the officer's college that are awaiting approval.

    Parameters:
        current_user_id (UUID): User ID of the campus placement officer.

    Returns:
        List[CampusDriveJobOut]: List of pending campus drive jobs.
    """
    try:
        result = await db.execute(
            select(CampusPlacementOfficer).filter_by(user_id=current_user_id)
        )
        officer = result.scalars().first()
        if not officer:
            raise HTTPException(
                status_code=404, detail="Campus placement officer not found"
            )
        return await get_pending_jobs_for_college(db, officer.college_id)
    except Exception as e:
        logger.error(f"Error fetching pending jobs: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to fetch pending campus drive jobs"
        )


@router.post("/approve", status_code=200)
async def approve_campus_job(
    request: CampusDriveApprovalRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Approves a specific job posting under a campus drive.

    - The approving user must be a campus placement officer.
    - Automatically maps the job to students of the batch linked to the drive.
    - Background tasks may include eligibility filtering or student job mapping.

    Parameters:
        request (CampusDriveApprovalRequest): Includes user_id and placement_id.

    Returns:
        Success message or placement approval confirmation.
    """
    try:
        result = await db.execute(
            select(CampusPlacementOfficer).filter_by(user_id=request.user_id)
        )
        officer = result.scalars().first()
        if not officer:
            raise HTTPException(
                status_code=404, detail="Campus placement officer not found"
            )

        return await approve_campus_drive_job(
            db=db,
            placement_id=request.placement_id,
            college_id=officer.college_id,
            background_tasks=background_tasks,
        )
    except Exception as e:
        logger.error(f"Failed to approve campus job: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to approve campus drive job"
        )


@router.get("/placement-matched-students")
async def placement_matched_students(
    user_id: UUID = Query(...),
    placement_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns students matching a campus placement's criteria.

    - Requires a valid officer and campus placement ID.
    - Matches students based on skills, batch, and other filters defined for the job.

    Query Parameters:
        user_id (UUID): User ID of the placement officer.
        placement_id (UUID): ID of the campus placement to match against.

    Returns:
        List of students who qualify for the placement criteria.
    """
    try:
        result = await db.execute(
            select(CampusPlacementOfficer).filter_by(user_id=user_id)
        )
        officer = result.scalars().first()
        if not officer:
            raise HTTPException(
                status_code=404, detail="Campus placement officer not found"
            )

        result = await db.execute(
            select(CampusPlacement).filter_by(placement_id=placement_id)
        )
        campus_placement = result.scalars().first()
        if not campus_placement:
            raise HTTPException(status_code=404, detail="Placement not found")

        return await get_placement_matched_students(
            campus_placement.job_id, officer.college_id, db
        )
    except Exception as e:
        logger.error(f"Error fetching matched students: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch matched students")


@router.get("/student-view", response_model=List[CampusJobStudentViewOut])
async def student_campus_jobs(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Fetches all eligible and active campus drive jobs available to a student.

    - Filters jobs based on the student's batch, eligibility, and job status.

    Parameters:
        user_id (UUID): The student's user ID.

    Returns:
        List of CampusJobStudentViewOut containing job details.
    """
    try:
        result = await db.execute(select(Student).filter_by(user_id=user_id))
        student = result.scalars().first()
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        return await get_student_campus_jobs(db, student.student_id)
    except Exception as e:
        logger.error(f"Error fetching campus jobs for student: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to fetch student campus jobs"
        )


@router.get("/officer/{user_id}/student-applicants-categorized")
async def get_categorized_applicants(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieves categorized applicant data for all campus jobs under an officer.

    - Groups applicants by their application status (e.g., Applied, Shortlisted, Rejected).
    - Useful for dashboards and analytics at the college/officer level.

    Path Parameters:
        user_id (UUID): Campus placement officer's user ID.

    Returns:
        Dict of job IDs and their associated applicant counts per status.
    """
    try:
        return await get_cumulative_applicants(user_id, db)
    except Exception as e:
        logger.error(f"Error fetching categorized applicants: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch applicant data")


@router.get("/officer/{user_id}/{job_id}/campus-applicants")
async def get_campus_applicants(
    user_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the list of students who have applied for a specific campus job.

    - Validates the officer’s authority to access the data.
    - Fetches all applicants submitted under a particular job ID.

    Path Parameters:
        user_id (UUID): Campus placement officer’s user ID.
        job_id (UUID): Job ID under the campus drive.

    Returns:
        List of applicants with application metadata.
    """
    try:
        return await get_applicants_for_job(user_id, job_id, db)
    except Exception as e:
        logger.error(f"Error fetching applicants for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch job applicants")
