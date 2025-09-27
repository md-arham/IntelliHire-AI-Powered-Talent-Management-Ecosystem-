from typing import List, Optional
import asyncio
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.services.email_service import smtp_email_service

from app.database.models import (
    TimeSlot,
    Student,
    JobApplication,
    JobApplicationStatus,
    EmployerProfile,
    PersonalInfo,
    User
)
from app.schemas.interview_scheduler_schemas import (
    TimeSlotBase
)

from app.utils.logger_config import isched_logger

async def get_timeslot(db: AsyncSession, slot_id: uuid.UUID) -> TimeSlot | None:
    stmt = select(TimeSlot).where(TimeSlot.slot_id == slot_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_timeslots_for_employer(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> Optional[List[TimeSlot]]:
    """
    Retrieve all time slots created by a specific employer.
    """
    stmt = select(EmployerProfile).where(EmployerProfile.user_id == user_id)
    result = await db.execute(stmt)
    employer = result.scalar_one_or_none()

    if not employer:
        isched_logger.info(f"Employer with the user_id {user_id} does not exist")
        return None

    stmt = select(TimeSlot).where(TimeSlot.employer_id == employer.employer_id)
    result = await db.execute(stmt)
    slots = result.scalars().all()

    # Enrich with student names if booked
    for slot in slots:
        if slot.is_booked and slot.booked_by:
            stmt = select(PersonalInfo).where(PersonalInfo.student_id == slot.booked_by)
            result = await db.execute(stmt)
            info = result.scalar_one_or_none()
            slot.student_name = info.full_name if info else None
        else:
            slot.student_name = None

    return slots

async def get_available_timeslots_for_student(
    db: AsyncSession,
    user_id: uuid.UUID
) -> List[TimeSlot] | None:
    """
    Retrieve all unbooked time slots for jobs the student has applied to.
    """
    result = await db.execute(
        select(Student).where(Student.user_id == user_id)
    )
    student = result.scalar_one_or_none()

    if not student:
        isched_logger.info(f"Student with user id {user_id} not found")
        return None

    result = await db.execute(
        select(JobApplication.job_id).where(JobApplication.student_id == student.student_id)
    )
    job_ids = [row[0] for row in result.all()]

    if not job_ids:
        return None

    result = await db.execute(
        select(TimeSlot).where(
            TimeSlot.job_id.in_(job_ids),
            ~TimeSlot.is_booked  # Unbooked slots only
        )
    )
    return result.scalars().all()


async def get_booked_timeslots_for_student(
    db: AsyncSession,
    user_id: uuid.UUID
) -> Optional[List[TimeSlot]]:
    """
    Retrieve all time slots that a student (by user_id) has booked.

    Args:
        db (AsyncSession): The async SQLAlchemy session.
        user_id (uuid.UUID): The user's UUID.

    Returns:
        Optional[List[TimeSlot]]: List of booked TimeSlot objects or None if student not found.
    """
    # 1. Find the student record
    result = await db.execute(
        select(Student).where(Student.user_id == user_id)
    )
    student = result.scalar_one_or_none()

    if not student:
        isched_logger.info(f"Student profile not found for user_id {user_id}")
        return None

    # 2. Fetch all booked slots for this student_id
    result = await db.execute(
        select(TimeSlot).where(
            TimeSlot.booked_by == student.student_id,
            TimeSlot.is_booked
        )
    )
    slots = result.scalars().all()

    return slots

async def create_timeslots(
    db: AsyncSession,
    job_id: uuid.UUID,
    slots_in: List[TimeSlotBase],
    user_id: uuid.UUID
) -> List[TimeSlot]:
    try:
        result = await db.execute(
        select(EmployerProfile).where(EmployerProfile.user_id == user_id)
    )
        employer = result.scalar_one_or_none()

        if not employer:
            detail = f"Employer with the user_id {user_id} does not exist"
            isched_logger.info(detail)
            raise ValueError(detail)

        to_add = []

        for slot in slots_in:
            dup_check = await db.execute(
                select(TimeSlot).where(
                    TimeSlot.job_id == job_id,
                    TimeSlot.start_time == slot.start_time,
                    TimeSlot.end_time == slot.end_time
                )
            )
            if dup_check.scalar_one_or_none():
                isched_logger.warning(
                    f"Duplicate TimeSlot attempt for job {job_id} by employer user_id {user_id}: "
                    f"{slot.start_time} - {slot.end_time}"
                )
                raise ValueError("One or more TimeSlots already exist for the given ranges.")

            to_add.append(
                TimeSlot(
                    job_id=job_id,
                    employer_id=employer.employer_id,
                    start_time=slot.start_time,
                    end_time=slot.end_time
                )
            )

        db.add_all(to_add)
        await db.commit()
        for obj in to_add:
            await db.refresh(obj)
        return to_add
    except SQLAlchemyError as e:
        await db.rollback()
        isched_logger.error(f"Error creating timeslots batch: {e}")
        raise ValueError(str(e))



async def book_timeslot(
    db: AsyncSession,
    slot_id: uuid.UUID,
    user_id: uuid.UUID,
    nowait: bool = False
) -> Optional[TimeSlot]:
    try:
        # Fetch student
        result = await db.execute(
            select(Student).where(Student.user_id == user_id)
        )
        student = result.scalar_one_or_none()
        if not student:
            detail = f"Student with user id {user_id} not found"
            isched_logger.info(detail)
            raise ValueError(detail)
        

        # Find the job_id for this slot (no lock yet)
        job_id = (
                await db.execute(
                select(TimeSlot.job_id).where(TimeSlot.slot_id == slot_id)
            )
        ).scalar_one_or_none()
        if not job_id:
            detail = f"Job id not found for the slot {slot_id}"
            isched_logger.info(detail)
            raise ValueError(detail)

        # Verify student applied *and* is shortlisted
        result = await db.execute(
            select(JobApplication).where(
                JobApplication.job_id == job_id,
                JobApplication.student_id == student.student_id,
                JobApplication.status == JobApplicationStatus.Shortlisted
            )
        )
        application = result.scalar_one_or_none()
        if not application:
            detail = f"Student {student.student_id} has no shortlisted application for job {job_id}"
            isched_logger.info(detail)
            raise ValueError(detail)

        # Prevent re-booking: has this student already booked any slot for this job?
        result = await db.execute(
            select(TimeSlot).where(
                TimeSlot.job_id == job_id,
                TimeSlot.booked_by == student.student_id
            )
        )
        if result.scalar_one_or_none():
            detail = f"Student {student.student_id} already has a booking for job {job_id}"
            isched_logger.info(detail)
            raise ValueError(detail)


        # Acquire lock on slot (pessimistic)
        stmt = (
            select(TimeSlot)
            .where(TimeSlot.slot_id == slot_id)
            .with_for_update(nowait=nowait)
        )
        result = await db.execute(stmt)
        timeslot = result.scalar_one_or_none()

        if not timeslot or timeslot.is_booked:
            await db.rollback()
            raise ValueError(f"Time slot {slot_id} already booked or unavailable")

        # Mark booked
        timeslot.is_booked = True
        timeslot.booked_by = student.student_id

        await db.commit()
        await db.refresh(timeslot)

        email, employer_name, student_name = await data_for_email(db, timeslot.employer_id, student.student_id)
        try:
            asyncio.create_task(
                timeslot_booked_email(email, employer_name, student_name)
            )
        except Exception as bg_err:
            isched_logger.error(f"Failed to schedule booking email task: {bg_err}", exc_info=True)


        return timeslot

    except OperationalError as op_err:
        await db.rollback()
        detail = f"Pessimistic lock not available for slot {slot_id}: {op_err}"
        isched_logger.warning(detail)
        raise ValueError(detail)

    except SQLAlchemyError as db_err:
        await db.rollback()
        detail = f"Database error booking slot {slot_id} for student with user_id {user_id}: {db_err}"
        isched_logger.error(
            detail,
            exc_info=True
        )
        raise ValueError(detail)
    

async def data_for_email(db: AsyncSession, employer_id: str, student_id: str):
    
    # 1. Get the user_id from EmployerProfile
    user_id = await db.execute(
        select(EmployerProfile.user_id)
        .where(EmployerProfile.employer_id == employer_id)
    )
    user_id = user_id.scalar_one_or_none()
    if user_id is None:
        raise ValueError(f"No EmployerProfile found for {employer_id}")

    # 2. Get the email from User
    result = await db.execute(
        select(User.email, User.full_name)
        .where(User.user_id == user_id)
    )
    row = result.one_or_none()
    if not row:
        raise ValueError(f"No User found with user_id {user_id}")
    employer_email, employer_name = row

    # 3. Fetch student personal info
    result = await db.execute(
        select(PersonalInfo.full_name)
        .where(PersonalInfo.student_id == student_id)
    )
    student_name = result.scalar_one_or_none() or "A student"

    return employer_email, employer_name, student_name



async def timeslot_booked_email(
    employer_email: str,
    employer_name: str,
    student_name: str,
) -> dict:
    """
    Send a notification email to the employer when a student books a timeslot.
    """
    # 4. Build subject and bodies
    subject = f"{student_name} just booked an interview slot"
    text_content = (
        f"Hello {employer_name},\n\n"
        f"{student_name} has booked an interview slot for your posting.\n"
        "Please check your dashboard for details.\n\n"
        "Best,\nInterview Scheduler Bot"
    )
    html_content = (
        f"<p>Hello {employer_name},</p>"
        f"<p><strong>{student_name}</strong> has booked an interview slot for your posting.</p>"
        "<p>Please check your dashboard for details.</p>"
        "<p>Best,<br>Interview Scheduler Bot</p>"
    )

    # 5. Send the email
    response = await smtp_email_service.send_email(
        to_email=employer_email,
        subject=subject,
        html_content=html_content,
        text_content=text_content
    )
    isched_logger.info(response)
    return response
