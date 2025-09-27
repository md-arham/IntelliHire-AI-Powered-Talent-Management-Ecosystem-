import os
import uuid
import shutil
import secrets
import pandas as pd

from app.utils.email_notifications import send_email_with_attachment
from sqlalchemy.future import select
from fastapi import HTTPException, UploadFile, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from typing import List, Dict, Any
from uuid import UUID
from io import BytesIO
from starlette.datastructures import UploadFile as StarletteUploadFile
import zipfile

from app.utils.logger_config import logger
from app.schemas.campusplacement_schemas import (
    StudentWithApplicationsResponse,
    StudentRegistrationCollegeID,
)
from app.database.models import (
    User,
    CampusPlacementOfficer,
    StudentBatch,
    Student,
    JobApplication,
    PlacementResource,
    JobPosting,
    RecommendedJob,
    Aspiration,
)
from app.database.models.enums_models import JobApplicationStatus
from app.utils.excel_helpers import (
    create_excel_with_credentials,
    create_resume_version_profile_wrapper,
    get_or_create_student_batch,
    map_excel_columns,
)
from app.schemas.auth_schemas import UserRole
from app.utils.settings import settings
from sqlalchemy import func
from sqlalchemy import distinct
from passlib.context import CryptContext
from sqlalchemy.orm import selectinload
from app.utils.db_session_utils import run_with_new_session
import asyncio


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def get_students_by_batch(
    batch_year: int, officer_user_id: UUID, db: AsyncSession
) -> List[StudentWithApplicationsResponse]:
    """
    Retrieves all students from a specific batch year under the supervision of a given campus placement officer.
    Includes each student's applied companies and batch metadata.

    Args:
        batch_year (int): The academic batch year to filter students.
        officer_user_id (UUID): The user ID of the campus placement officer.
        db (AsyncSession): Database session for async operations.

    Raises:
        HTTPException:
            - 404 if the placement officer is not found.
            - 404 if no batches are found for the given year and college.

    Returns:
        List[StudentWithApplicationsResponse]: List of student profiles enriched with applied companies and batch details.
    """
    res = await db.execute(
        select(CampusPlacementOfficer).filter_by(user_id=officer_user_id)
    )
    officer = res.scalar_one_or_none()
    if not officer:
        logger.info("Campus Placement officer not found")
        raise HTTPException(
            status_code=404, detail="Campus Placement Officer not found"
        )

    res = await db.execute(
        select(StudentBatch).filter_by(
            college_id=officer.college_id, batch_year=batch_year
        )
    )
    batches = res.scalars().all()
    if not batches:
        logger.info("No batch records found")
        raise HTTPException(status_code=404, detail="Batch not found")

    batch_ids = [b.batch_id for b in batches]

    res = await db.execute(
        select(Student)
        .options(
            joinedload(Student.user),
            joinedload(Student.applications).joinedload(JobApplication.job),
        )
        .filter(Student.batch_id.in_(batch_ids))
    )
    students = res.unique().scalars().all()

    output = []
    for student in students:
        applied_companies = list(
            {app.job.company_name for app in student.applications if app.job}
        )

        # You can enrich this with actual batch info if needed
        batch = next((b for b in batches if b.batch_id == student.batch_id), None)

        output.append(
            StudentWithApplicationsResponse(
                student_id=student.student_id,
                email=student.email,
                full_name=student.user.full_name if student.user else None,
                profile_img_path=student.user.profile_img_path
                if student.user
                else None,
                batch_year=batch.batch_year if batch else None,
                department=batch.department if batch else None,
                section=batch.section if batch else None,
                applied_companies=applied_companies,
            )
        )
    return output


async def upload_resource(
    current_user_id: UUID,
    title: str,
    description: str,
    file: UploadFile,
    db: AsyncSession,
):
    """
    Allows a campus placement officer to upload a new placement preparation resource
    (e.g., PDFs, guides, documents) for their associated college.

    Args:
        current_user_id (UUID): The ID of the authenticated user performing the upload.
        title (str): Title of the resource.
        description (str): A short description of the uploaded resource.
        file (UploadFile): The file being uploaded.
        db (AsyncSession): Active asynchronous database session.

    Raises:
        HTTPException:
            - 403 if the user is not a placement officer.
            - 404 if the placement officer profile is not found.
            - 500 if file saving fails.

    Returns:
        PlacementResource: The database object representing the uploaded resource.
    """
    res = await db.execute(select(User).filter_by(user_id=current_user_id))
    user = res.scalar_one_or_none()
    if not user or user.role != UserRole.campus_officer:
        raise HTTPException(
            status_code=403, detail="Only placement officers can upload resources"
        )

    res = await db.execute(
        select(CampusPlacementOfficer).filter_by(user_id=current_user_id)
    )
    officer = res.scalar_one_or_none()
    if not officer:
        raise HTTPException(
            status_code=404, detail="Placement Officer profile not found."
        )

    os.makedirs(settings.CAMPUS_RESOURCE_PATH, exist_ok=True)
    file_ext = file.filename.split(".")[-1]
    saved_path = os.path.join(
        settings.CAMPUS_RESOURCE_PATH, f"{uuid.uuid4()}.{file_ext}"
    )

    try:
        with open(saved_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"File saving failed: {e}")
        raise HTTPException(status_code=500, detail="File saving failed")

    resource = PlacementResource(
        uploaded_by_officer_id=officer.officer_id,
        college_id=officer.college_id,
        title=title,
        description=description,
        file_path=saved_path,
    )
    db.add(resource)
    await db.commit()
    await db.refresh(resource)
    return resource


async def delete_resource(resource_id: UUID, current_user_id: UUID, db: AsyncSession):
    """
    Deletes a placement resource uploaded by the currently authenticated campus officer.
    Ensures the officer can only delete resources they uploaded.

    Args:
        resource_id (UUID): ID of the resource to be deleted.
        current_user_id (UUID): ID of the user requesting deletion.
        db (AsyncSession): Active asynchronous database session.

    Raises:
        HTTPException:
            - 403 if the user is not authorized to delete the resource.
            - 404 if the user or resource is not found.
            - 500 if there is a file deletion error.
    """
    res = await db.execute(select(User).filter_by(user_id=current_user_id))
    user = res.scalar_one_or_none()
    if not user or user.role != UserRole.campus_officer:
        raise HTTPException(
            status_code=403, detail="Only placement officers can delete resources."
        )

    res = await db.execute(
        select(CampusPlacementOfficer).filter_by(user_id=current_user_id)
    )
    officer = res.scalar_one_or_none()
    if not officer:
        raise HTTPException(
            status_code=404, detail="Placement officer profile not found."
        )

    res = await db.execute(select(PlacementResource).filter_by(resource_id=resource_id))
    resource = res.scalar_one_or_none()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found.")

    if resource.uploaded_by_officer_id != officer.officer_id:
        raise HTTPException(
            status_code=403, detail="You can only delete resources uploaded by you."
        )

    try:
        if os.path.exists(resource.file_path):
            os.remove(resource.file_path)
    except Exception as e:
        logger.error(f"Failed to delete file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {e}")

    await db.delete(resource)
    await db.commit()


async def get_resources_by_user_college(current_user_id: UUID, db: AsyncSession):
    """
    Fetches all placement resources available to a student or campus placement officer
    based on the college they belong to.

    Args:
        current_user_id (UUID): ID of the requesting user.
        db (AsyncSession): Active asynchronous database session.

    Raises:
        HTTPException:
            - 403 if the user role is not permitted.
            - 404 if user profile is missing (student or officer).

    Returns:
        List[PlacementResource]: All placement resources for the user’s associated college, sorted by upload time (newest first).
    """
    res = await db.execute(select(User).filter_by(user_id=current_user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if user.role == UserRole.campus_officer:
        res = await db.execute(
            select(CampusPlacementOfficer).filter_by(user_id=user.user_id)
        )
        officer = res.scalar_one_or_none()
        if not officer:
            raise HTTPException(
                status_code=404, detail="Placement Officer profile does not exist"
            )
        college_id = officer.college_id
    elif user.role == UserRole.student:
        res = await db.execute(select(Student).filter_by(user_id=user.user_id))
        student = res.scalar_one_or_none()
        if not student:
            raise HTTPException(
                status_code=404, detail="Student Profile does not exist"
            )
        college_id = student.college_id
    else:
        raise HTTPException(
            status_code=403,
            detail="Only students or placement officers can view resources",
        )

    res = await db.execute(
        select(PlacementResource)
        .filter_by(college_id=college_id)
        .order_by(PlacementResource.created_at.desc())
    )
    return res.scalars().all()


async def download_resource(resource_id: UUID, current_user_id: UUID, db: AsyncSession):
    """
    Downloads a placement resource if the requesting user belongs to the same college.

    Verifies the user role (student or officer), retrieves the corresponding college,
    and checks whether the requested resource belongs to that college before serving it.

    Args:
        resource_id (UUID): ID of the resource to be downloaded.
        current_user_id (UUID): ID of the requesting user.
        db (AsyncSession): Async database session.

    Raises:
        HTTPException:
            - 404 if user profile or resource not found.
            - 403 if user is unauthorized or from a different college.

    Returns:
        FileResponse: A file stream of the requested resource.
    """
    res = await db.execute(select(User).filter_by(user_id=current_user_id))
    user = res.scalar_one_or_none()

    res = await db.execute(select(PlacementResource).filter_by(resource_id=resource_id))
    resource = res.scalar_one_or_none()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found.")

    if user.role == UserRole.campus_officer:
        res = await db.execute(
            select(CampusPlacementOfficer).filter_by(user_id=current_user_id)
        )
        officer = res.scalar_one_or_none()
        if not officer:
            raise HTTPException(
                status_code=404, detail="Placement officer profile not found"
            )
        user_college_id = officer.college_id
    elif user.role == UserRole.student:
        res = await db.execute(select(Student).filter_by(user_id=current_user_id))
        student = res.scalar_one_or_none()
        if not student:
            raise HTTPException(status_code=404, detail="Student profile not found")
        user_college_id = student.college_id
    else:
        raise HTTPException(status_code=403, detail="Not authorized")

    if resource.college_id != user_college_id:
        raise HTTPException(
            status_code=403, detail="You are not authorized to access this file."
        )

    return FileResponse(
        path=resource.file_path,
        filename=os.path.basename(resource.file_path),
        media_type="application/octet-stream",
    )


async def get_analytics_counts(current_user_id: UUID, db: AsyncSession):
    """
    Returns analytics summary for a campus placement officer's dashboard.

    Provides metrics including total students registered, students placed,
    students in interview process, total jobs posted, and number of companies actively hiring.

    Args:
        current_user_id (UUID): ID of the campus placement officer.
        db (AsyncSession): Async database session.

    Raises:
        HTTPException: 404 if officer profile not found.

    Returns:
        dict: {
            'students_registered': int,
            'students_placed': int,
            'students_in_progress': int,
            'total_jobs': int,
            'active_companies': int
        }
    """
    placement_officer = (
        await db.execute(
            select(CampusPlacementOfficer).filter_by(user_id=current_user_id)
        )
    ).scalar_one_or_none()

    if not placement_officer:
        raise HTTPException(
            status_code=404, detail="Campus Placement Officer not found"
        )

    college_id = placement_officer.college_id

    students_registered = (
        await db.execute(
            select(func.count()).select_from(Student).filter_by(college_id=college_id)
        )
    ).scalar()

    students_placed = (
        await db.execute(
            select(func.count(distinct(JobApplication.student_id)))
            .join(Student)
            .filter(
                Student.college_id == college_id,
                JobApplication.status.in_(
                    [JobApplicationStatus.Hired, JobApplicationStatus.Offered]
                ),
            )
        )
    ).scalar()

    students_in_progress = (
        await db.execute(
            select(func.count(distinct(JobApplication.student_id)))
            .join(Student)
            .filter(
                Student.college_id == college_id,
                JobApplication.status.in_(
                    [JobApplicationStatus.InProgress, JobApplicationStatus.Shortlisted]
                ),
            )
        )
    ).scalar()

    total_jobs = (
        await db.execute(select(func.count()).select_from(JobPosting))
    ).scalar()

    active_companies = (
        await db.execute(
            select(func.count(distinct(JobPosting.employer_id)))
            .join(JobApplication, JobPosting.job_id == JobApplication.job_id)
            .join(Student, JobApplication.student_id == Student.student_id)
            .filter(Student.college_id == college_id)
        )
    ).scalar()

    return {
        "students_registered": students_registered,
        "students_placed": students_placed,
        "students_in_progress": students_in_progress,
        "total_jobs": total_jobs,
        "active_companies": active_companies,
    }


async def get_all_active_jobs(db: AsyncSession) -> List[JobPosting]:
    """
    Retrieves all job postings marked as active, ordered by posting date.

    Args:
        db (AsyncSession): Async database session.

    Returns:
        List[JobPosting]: A list of currently active job postings.
    """
    result = await db.execute(
        select(JobPosting)
        .filter(JobPosting.is_active)
        .order_by(JobPosting.posted_at.desc())
    )
    return result.scalars().all()


async def get_students_by_batch_year(db: AsyncSession, batch_year: int):
    """
    Fetches all students who belong to a specific batch year, across all colleges.

    Args:
        db (AsyncSession): Async database session.
        batch_year (int): Year of the student batch.

    Raises:
        HTTPException: 500 in case of database query failure.

    Returns:
        List[Student]: A list of students from the given batch year.
    """
    try:
        batches = (
            (
                await db.execute(
                    select(StudentBatch).filter(StudentBatch.batch_year == batch_year)
                )
            )
            .scalars()
            .all()
        )

        batch_ids = [b.batch_id for b in batches]

        students = (
            (await db.execute(select(Student).filter(Student.batch_id.in_(batch_ids))))
            .scalars()
            .all()
        )

        return students
    except Exception as e:
        logger.error(f"Failed to fetch students by batch year {batch_year}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to fetch students by batch year."
        )


async def recommend_job_to_batch(
    db: AsyncSession, job_id: UUID, batch_year: int, officer_id: UUID
):
    """
    Recommends a job posting to all students of a particular batch year
    if they have not already received a recommendation for it.

    Args:
        db (AsyncSession): Async database session.
        job_id (UUID): ID of the job to recommend.
        batch_year (int): Student batch year.
        officer_id (UUID): ID of the recommending placement officer.

    Raises:
        HTTPException:
            - 404 if the job or batch or students not found.
            - 500 on any unexpected error.

    Returns:
        int: Count of new job recommendations created.
    """
    try:
        job = (
            await db.execute(
                select(JobPosting).filter_by(job_id=job_id, is_active=True)
            )
        ).scalar_one_or_none()

        if not job:
            raise HTTPException(status_code=404, detail="The Job does not exist in")

        batches = (
            (
                await db.execute(
                    select(StudentBatch).filter(StudentBatch.batch_year == batch_year)
                )
            )
            .scalars()
            .all()
        )

        if not batches:
            raise HTTPException(
                status_code=404, detail="The Batch Year does not exist in this college"
            )

        students = await get_students_by_batch_year(db, batch_year)
        if not students:
            raise HTTPException(
                status_code=404, detail="No Students found in this batch Year"
            )

        new_recommendations = []
        for student in students:
            exists = (
                await db.execute(
                    select(RecommendedJob).filter_by(
                        student_id=student.student_id, job_id=job_id
                    )
                )
            ).scalar_one_or_none()
            if not exists:
                new_recommendations.append(
                    RecommendedJob(
                        student_id=student.student_id,
                        job_id=job_id,
                        recommended_by_officer_id=officer_id,
                    )
                )

        if new_recommendations:
            db.add_all(new_recommendations)
            await db.commit()

        return len(new_recommendations)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error recommending job: {e}")


async def get_batch_years_for_college(db: AsyncSession, college_id: UUID):
    """
    Retrieves all distinct batch years associated with a specific college.

    Args:
        db (AsyncSession): Async database session.
        college_id (UUID): Unique identifier of the college.

    Raises:
        HTTPException: 500 if database query fails.

    Returns:
        List[int]: A list of unique batch years for the college.
    """
    try:
        result = await db.execute(
            select(StudentBatch.batch_year).filter_by(college_id=college_id).distinct()
        )
        return [row[0] for row in result.all()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching batch years: {e}")


async def get_recommended_jobs_for_student(db: AsyncSession, user_id: UUID):
    """
    Fetches all job postings that have been recommended to a specific student.

    Validates that the user is a student and retrieves all related recommended jobs,
    ordered by the date they were posted.

    Args:
        db (AsyncSession): Async database session.
        user_id (UUID): ID of the student user.

    Raises:
        HTTPException: 500 if database access fails.
        ValueError: If the user is not a student or does not exist.

    Returns:
        List[JobPosting]: List of recommended job postings.
    """
    try:
        result = await db.execute(
            select(User)
            .options(selectinload(User.student_profile))
            .filter_by(user_id=user_id)
        )
        user = result.scalar_one_or_none()

        if not user or not user.student_profile:
            raise ValueError("User is not a student or does not exist")

        student_id = user.student_profile.student_id

        result = await db.execute(
            select(JobPosting)
            .join(RecommendedJob, JobPosting.job_id == RecommendedJob.job_id)
            .filter(RecommendedJob.student_id == student_id)
            .order_by(JobPosting.posted_at.desc())
        )

        return result.scalars().all()

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching recommended jobs: {e}"
        )


def calculate_dynamic_batch_size(
    total_students: int, min_batch: int = 10, max_batch: int = 50
) -> int:
    """
    Calculate an optimal batch size for processing students based on total count.

    For small datasets (<= 100), uses 20% of total students with a lower bound.
    For medium datasets (<= 1000), uses 20% with an upper bound.
    For large datasets (> 1000), uses 10% with min-max constraints.

    Args:
        total_students (int): Total number of students to process.
        min_batch (int): Minimum allowed batch size. Default is 10.
        max_batch (int): Maximum allowed batch size. Default is 50.

    Returns:
        int: Computed optimal batch size within defined bounds.
    """
    if total_students <= 100:
        # For small datasets, use 20% of total students
        batch_size = max(min_batch, total_students // 5)
    elif total_students <= 1000:
        # For medium datasets, use 20% with upper bound
        batch_size = min(max_batch, total_students // 5)
    else:
        # For large datasets, use fixed percentage with bounds
        batch_size = min(max_batch, max(min_batch, total_students // 10))

    return min(max_batch, max(min_batch, batch_size))


async def register_student_v2_without_resume_processing(
    form: StudentRegistrationCollegeID,
    db: AsyncSession,
    batch_id: str = None,
):
    """
    Registers a student account without handling resume upload.

    Checks for duplicate email, creates user and student records,
    and stores any provided aspirations linked to the student.

    Args:
        form (StudentRegistrationCollegeID): Registration form with student details.
        db (AsyncSession): Async database session.
        batch_id (str, optional): Optional batch ID to associate with the student.

    Raises:
        HTTPException:
            - 400 if the email is already registered.
            - 500 for unexpected errors during registration.

    Returns:
        dict: Contains success message, user_id, name, email, and role.
    """
    try:
        result = await db.execute(select(User).filter(User.email == form.email))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already registered")

        user = User(
            user_id=uuid.uuid4(),
            full_name=form.full_name,
            email=form.email,
            password_hash=pwd_context.hash(form.password),
            role="student",
        )
        db.add(user)
        await db.flush()

        student = Student(
            student_id=uuid.uuid4(),
            user_id=user.user_id,
            college_id=form.college_id,
            email=form.email,
            batch_id=batch_id,
        )
        db.add(student)
        await db.flush()

        for asp in form.aspirations:
            db.add(
                Aspiration(
                    aspiration_id=uuid.uuid4(),
                    student_id=student.student_id,
                    aspiration_text=asp,
                )
            )

        await db.commit()
        return {
            "message": "registered successfully",
            "user_id": str(user.user_id),
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role,
        }

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error registering student: {e}")


async def process_single_student_concurrent(
    student_data: Dict[str, Any],
    college_id: str,
    batch_id_map: Dict[int, str],
    existing_emails: set,
    semaphore: asyncio.Semaphore,
) -> Dict[str, Any]:
    """
    Process a single student with concurrency control.

    Args:
        student_data: Student information dictionary
        college_id: College ID
        batch_id_map: Mapping of batch years to batch IDs
        existing_emails: Set of already registered emails
        semaphore: Semaphore for concurrency control

    Returns:
        Dict containing processing result
    """
    async with semaphore:
        try:
            full_name = student_data["full_name"]
            email = student_data["email"]
            student_id = student_data["student_id"]
            batch_year = student_data["batch_year"]
            resume_bytes = student_data["resume_bytes"]

            # Check if user already exists (from pre-fetched data)
            if email in existing_emails:
                return {
                    "student_name": full_name,
                    "login_email": email,
                    "password": "",
                    "status": "already registered",
                }

            # Generate password and create registration form
            password = secrets.token_urlsafe(10)
            batch_id = batch_id_map.get(batch_year)

            form = StudentRegistrationCollegeID(
                full_name=full_name,
                email=email,
                password=password,
                confirm_password=password,
                college_id=college_id,
                aspirations=[],
                batch=batch_year,
            )

            # Register student in separate session
            async def register_student_wrapper(db):
                return await register_student_v2_without_resume_processing(
                    form, db, batch_id=batch_id
                )

            reg_result = await run_with_new_session(register_student_wrapper)

            # Create resume version in separate session
            async def create_resume_wrapper(db):
                return await create_resume_version_profile_wrapper(
                    db,
                    user_id=reg_result["user_id"],
                    resume_type="Uploaded",
                    resume_name=f"{student_id}.pdf",
                    file=StarletteUploadFile(
                        filename=f"{student_id}.pdf",
                        file=BytesIO(resume_bytes),
                    ),
                )

            await run_with_new_session(create_resume_wrapper)

            return {
                "student_name": full_name,
                "login_email": email,
                "password": password,
                "status": "registered",
            }

        except Exception as e:
            logger.error(
                f"Error processing {student_data.get('full_name', 'Unknown')}: {e}"
            )
            return {
                "student_name": student_data.get("full_name", "Unknown"),
                "login_email": student_data.get("email", "Unknown"),
                "password": "",
                "status": f"failed: {str(e)}",
            }


async def process_student_batch_concurrent(
    student_batch: List[Dict[str, Any]], college_id: str, max_concurrent: int = 5
) -> List[Dict[str, Any]]:
    """
    Process a batch of students with concurrent execution.

    Args:
        student_batch: List of student data dictionaries
        college_id: College ID
        max_concurrent: Maximum concurrent operations per batch

    Returns:
        List of processing results
    """
    if not student_batch:
        return []

    # Pre-fetch required data in a single session
    async def get_batch_prerequisites(db):
        # Get emails to check for existing users
        emails = [student["email"] for student in student_batch]
        existing_users_result = await db.execute(
            select(User.email).filter(User.email.in_(emails))
        )
        existing_emails = {row[0] for row in existing_users_result.fetchall()}

        # Get or create batch IDs for unique batch years
        batch_years = {s["batch_year"] for s in student_batch if s["batch_year"]}
        batch_id_map = {}
        for batch_year in batch_years:
            if batch_year:
                batch_id = await get_or_create_student_batch(db, college_id, batch_year)
                batch_id_map[batch_year] = batch_id

        return existing_emails, batch_id_map

    existing_emails, batch_id_map = await run_with_new_session(get_batch_prerequisites)

    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(max_concurrent)

    # Process students concurrently
    tasks = [
        process_single_student_concurrent(
            student_data, college_id, batch_id_map, existing_emails, semaphore
        )
        for student_data in student_batch
    ]

    # Wait for all tasks to complete
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle any exceptions that occurred
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Exception processing student {i}: {result}")
            student = student_batch[i]
            processed_results.append(
                {
                    "student_name": student.get("full_name", "Unknown"),
                    "login_email": student.get("email", "Unknown"),
                    "password": "",
                    "status": f"failed: {str(result)}",
                }
            )
        else:
            processed_results.append(result)

    return processed_results


async def process_bulk_student_registration_background(
    user_id: str,
    college_id: str,
    excel_content: bytes,
    zip_content: bytes,
):
    """
    Background task to process bulk student registration from an Excel file and ZIP of resumes.
    It handles batching and concurrency internally.

    Args:
        user_id (str): Campus placement officer's user ID
        college_id (str): College ID
        excel_content (bytes): Content of uploaded Excel file
        zip_content (bytes): Content of uploaded ZIP file with resumes
    """
    try:
        results = []

        # Parse Excel file
        df = pd.read_excel(BytesIO(excel_content))
        if df.empty:
            logger.error("Uploaded Excel is empty")
            return
        df = map_excel_columns(df)

        # Validate required columns
        required_columns = ["full_name", "email", "student_id"]
        missing = [col for col in required_columns if col not in df.columns]
        if missing:
            logger.error(f"Missing columns: {', '.join(missing)}")
            return

        # Extract resume files
        resume_files = {}
        with zipfile.ZipFile(BytesIO(zip_content), "r") as zip_ref:
            for file_name in zip_ref.namelist():
                if not file_name.lower().endswith(".pdf"):
                    continue
                student_id_key = os.path.splitext(os.path.basename(file_name))[
                    0
                ].lower()
                resume_files[student_id_key] = zip_ref.read(file_name)

        # Get officer email
        async def get_officer_email(db):
            result = await db.execute(select(User).filter_by(user_id=user_id))
            officer_user = result.scalar_one_or_none()
            return officer_user.email if officer_user else None

        officer_email = await run_with_new_session(get_officer_email)
        if not officer_email:
            logger.error(f"Officer user not found: {user_id}")
            return

        # Prepare student data with validation
        student_data = []
        for _, row in df.iterrows():
            try:
                full_name = str(row["full_name"]).strip()
                email = str(row["email"]).strip().lower()
                student_id = str(row["student_id"]).strip().lower()

                # Handle batch information
                batch_year = None
                if "batch" in df.columns and pd.notna(row.get("batch")):
                    batch_year = int(row["batch"])

                # Check if resume exists
                resume_bytes = resume_files.get(student_id)
                if not resume_bytes:
                    results.append(
                        {
                            "student_name": full_name,
                            "login_email": email,
                            "password": "",
                            "status": "failed: resume not found",
                        }
                    )
                    continue

                student_data.append(
                    {
                        "full_name": full_name,
                        "email": email,
                        "student_id": student_id,
                        "batch_year": batch_year,
                        "resume_bytes": resume_bytes,
                    }
                )

            except Exception as e:
                logger.error(f"Error preparing data for {row.get('full_name')}: {e}")
                results.append(
                    {
                        "student_name": row.get("full_name", "Unknown"),
                        "login_email": row.get("email", "Unknown"),
                        "password": "",
                        "status": f"failed: data preparation error - {str(e)}",
                    }
                )

        if not student_data:
            logger.warning("No valid student data to process")
            if results:  # Send email with failed results
                await _send_results_email(results, officer_email)
            return

        # Calculate dynamic batch size
        total_students = len(student_data)
        batch_size = calculate_dynamic_batch_size(total_students)
        max_concurrent_per_batch = min(
            5, max(2, batch_size // 4)
        )  # 25% of batch size, bounded

        logger.info(
            f"Processing {total_students} students in batches of {batch_size} "
            f"with max {max_concurrent_per_batch} concurrent operations per batch"
        )

        # Process students in batches with concurrent processing
        for i in range(0, len(student_data), batch_size):
            batch = student_data[i : i + batch_size]
            batch_number = (i // batch_size) + 1
            total_batches = (len(student_data) + batch_size - 1) // batch_size

            logger.info(
                f"Processing batch {batch_number}/{total_batches} ({len(batch)} students)"
            )

            try:
                batch_results = await process_student_batch_concurrent(
                    batch, college_id, max_concurrent_per_batch
                )
                results.extend(batch_results)

                # Log batch completion
                batch_registered = len(
                    [r for r in batch_results if r["status"] == "registered"]
                )
                logger.info(
                    f"Batch {batch_number} completed: {batch_registered}/{len(batch)} registered"
                )

            except Exception as e:
                logger.error(f"Error processing batch {batch_number}: {e}")
                # Add failed results for this batch
                for student in batch:
                    results.append(
                        {
                            "student_name": student["full_name"],
                            "login_email": student["email"],
                            "password": "",
                            "status": f"failed: batch processing error - {str(e)}",
                        }
                    )

        # Send results email
        if results:
            await _send_results_email(results, officer_email)

            # Log final summary
            registered_count = len([r for r in results if r["status"] == "registered"])
            logger.info(
                f"Bulk registration completed: {registered_count}/{len(results)} students registered"
            )

    except Exception as e:
        logger.error(f"Bulk registration failed: {e}")


async def _send_results_email(results: List[Dict[str, Any]], officer_email: str):
    """
    Sends an email to the campus officer with Excel report of registration results.

    Args:
        results (List[Dict]): List of student registration outcomes
        officer_email (str): Email of the officer
    """
    try:
        excel_bytes = await create_excel_with_credentials(results)

        # Create summary statistics
        registered_count = len([r for r in results if r["status"] == "registered"])
        already_registered_count = len(
            [r for r in results if r["status"] == "already registered"]
        )
        failed_count = len([r for r in results if r["status"].startswith("failed")])

        await send_email_with_attachment(
            sender=settings.SENDER_EMAIL,
            password=settings.APP_PASSWORD,
            recipients=[officer_email],
            subject="InternHire - Bulk Student Registration Report",
            body=(
                f"Bulk Student Registration Summary:\n\n"
                f"Successfully Registered: {registered_count}\n"
                f"Already Registered: {already_registered_count}\n"
                f"Failed: {failed_count}\n"
                f"Total Processed: {len(results)}\n\n"
                f"Success Rate: {(registered_count / len(results) * 100):.1f}%\n\n"
                "Please find the detailed credentials and status report in the attached Excel file."
            ),
            file_bytes=excel_bytes,
            filename="student_credentials.xlsx",
        )
    except Exception as e:
        logger.error(f"Email sending failed: {e}")


async def handle_bulk_student_upload(
    user_id: str,
    excel_file: UploadFile,
    resume_zip: UploadFile,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
):
    """
    Initiates a background task for bulk student registration.

    Args:
        user_id (str): Campus placement officer's user ID
        excel_file (UploadFile): Excel file with student data
        resume_zip (UploadFile): ZIP file of student resumes
        db (AsyncSession): Database session
        background_tasks (BackgroundTasks): FastAPI background task handler
    """
    try:
        result = await db.execute(
            select(CampusPlacementOfficer).filter_by(user_id=user_id)
        )
        officer = result.scalar_one_or_none()
        if not officer:
            raise HTTPException(status_code=404, detail="Officer not found")
        college_id = officer.college_id

        excel_content = await excel_file.read()
        zip_content = await resume_zip.read()

        df = pd.read_excel(BytesIO(excel_content))
        df = map_excel_columns(df)

        required = ["full_name", "email", "student_id"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise HTTPException(400, detail=f"Missing: {', '.join(missing)}")

        # Calculate expected batch size for user information
        total_students = len(df)
        batch_size = calculate_dynamic_batch_size(total_students)

        background_tasks.add_task(
            process_bulk_student_registration_background,
            user_id=user_id,
            college_id=college_id,
            excel_content=excel_content,
            zip_content=zip_content,
        )

        return {
            "message": f"Bulk registration started for {total_students} students.",
            "total_students": total_students,
            "estimated_batch_size": batch_size,
            "status": "processing",
            "note": "You will receive an email with the registration results once processing is complete.",
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error initiating bulk upload: {e}"
        )
