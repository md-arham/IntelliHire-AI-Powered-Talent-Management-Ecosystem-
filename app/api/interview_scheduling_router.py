from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from app.database.db import get_db
from app.schemas.interview_scheduler_schemas import (
    TimeSlotOut,
    TimeSlotOutEmployer,
    TimeSlotsCreate
)
from app.services.interview_scheduler_service import (
    create_timeslots,
    get_timeslots_for_employer,
    get_available_timeslots_for_student,
    get_booked_timeslots_for_student,
    book_timeslot
)

router = APIRouter(prefix="/api/timeslots", tags=['Time-Slot Selection'])

@router.post(
    "/employers/{employer_id}/post/",
    response_model=List[TimeSlotOut],
    status_code=status.HTTP_201_CREATED,
)
async def employer_create_timeslots(
    employer_id: uuid.UUID,
    info: TimeSlotsCreate,
    db: AsyncSession = Depends(get_db),
) -> List[TimeSlotOut]:
    try:
        created = await create_timeslots(db, info.job_id, info.slots, employer_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    return created

@router.get(
    "/employers/{employer_id}/",
    response_model=List[TimeSlotOutEmployer],
)
async def employer_list_timeslots(
    employer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> List[TimeSlotOutEmployer]:
    all_slots = await get_timeslots_for_employer(db, employer_id)
    if not all_slots:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No timeslots found for this employer with user_id {employer_id}",
        )
    return all_slots

@router.get(
    "/students/{student_id}/available/",
    response_model=List[TimeSlotOut],
)
async def student_get_available_timeslots(
    student_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> List[TimeSlotOut]:
    # List all available (unbooked) slots for jobs the student applied to
    available = await get_available_timeslots_for_student(db, student_id)
    if not available:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No available time slots found for this student with user_id {student_id}",
        )
    return available

@router.get(
    "/students/{user_id}/booked/",
    response_model=List[TimeSlotOut]
)
async def student_get_booked_timeslots(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> List[TimeSlotOut]:
    booked = await get_booked_timeslots_for_student(db, user_id)
    if not booked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No booked time slots found for student user_id {user_id}"
        )
    return booked



@router.post(
    "/students/{user_id}/{slot_id}/book/",
    response_model=TimeSlotOut,
)
async def student_book_timeslot(
    user_id: uuid.UUID,
    slot_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> TimeSlotOut:
    try:
        ts = await book_timeslot(db, slot_id, user_id, nowait=True)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_417_EXPECTATION_FAILED,
            detail=str(e)
        )
    return ts