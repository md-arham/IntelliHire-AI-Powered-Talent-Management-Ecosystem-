from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Optional

class TimeSlotBase(BaseModel):
    start_time: datetime
    end_time: datetime

class TimeSlotsCreate(BaseModel):
    job_id: UUID = Field(..., description="ID of the job for which slots are created")
    slots: List[TimeSlotBase] = Field(..., description="List of time slots to create")

class TimeSlotOut(TimeSlotBase):
    slot_id: UUID
    job_id: UUID
    employer_id: UUID
    is_booked: bool
    booked_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class TimeSlotOutEmployer(TimeSlotOut):
    student_name: Optional[str]
