from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from fastapi import HTTPException, status

from app.database.models import (
    JobApplication,
    Student,
    JobApplicationStatus
)


async def reject_student(
    db: AsyncSession,
    job_id: str,
    student_user_id: str
) -> dict:
    """
    Marks a student's job application as Rejected.

    Returns a dict with application_id and new status.
    """
    # 1. Fetch student record
    result = await db.execute(
        select(Student).where(Student.user_id == student_user_id)
    )
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with user_id {student_user_id} not found",
        )

    # 2. Fetch application record
    result = await db.execute(
        select(JobApplication).where(
            JobApplication.student_id == student.student_id,
            JobApplication.job_id == UUID(job_id)
        )
    )
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application for job {job_id} and student {student_user_id} not found",
        )

    # 3. Update status and commit
    application.status = JobApplicationStatus.Rejected
    await db.commit()
    await db.refresh(application)

    return {
        "application_id": str(application.application_id),
        "status": application.status.value,
        "student_id": str(student.student_id),
    }

async def shortlist_student(
    db: AsyncSession,
    job_id: str,
    student_user_id: str
) -> dict:
    """
    Marks a student's job application as Shortlisted and advances stage to L2.

    Returns a dict with application_id, new status, and current_stage.
    """
    # Fetch student record
    result = await db.execute(
        select(Student).where(Student.user_id == student_user_id)
    )
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with user_id {student_user_id} not found",
        )

    # Fetch application record
    result = await db.execute(
        select(JobApplication).where(
            JobApplication.student_id == student.student_id,
            JobApplication.job_id == UUID(job_id)
        )
    )
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application for job {job_id} and student {student_user_id} not found",
        )

    # Update status, stage and commit
    application.status = JobApplicationStatus.Shortlisted
    application.current_stage = "L2"
    await db.commit()
    await db.refresh(application)

    return {
        "application_id": str(application.application_id),
        "status": application.status.value,
        "current_stage": application.current_stage,
    }
