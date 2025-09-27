from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional, Any


class CampusDriveInitiateRequest(BaseModel):
    job_id: UUID
    college_id: UUID
    employer_user_id: UUID
    drive_id: UUID


class CampusDriveInitiateResponse(BaseModel):
    campus_placement_id: UUID
    cloned_job_id: UUID
    message: str
    created_at: datetime


class JobPostingOut(BaseModel):
    title: str
    company_name: str
    posted_at: datetime
    description: Optional[str]

    class Config:
        from_attributes = True


class CampusDriveJobOut(BaseModel):
    placement_id: UUID
    job_id: UUID
    job: JobPostingOut

    class Config:
        from_attributes = True


class CampusDriveApprovalRequest(BaseModel):
    user_id: UUID
    placement_id: UUID


class CampusJobStudentViewOut(BaseModel):
    job_id: UUID
    title: str
    description: str
    company_name: str
    location: Optional[str]
    posted_at: datetime

    class Config:
        from_attributes = True


class CampusDriveCreateRequest(BaseModel):
    officer_user_id: UUID
    drive_name: str
    start_date: datetime
    end_date: datetime
    target_batch_id: UUID
    min_cgpa: Optional[int] = None
    max_backlogs: Optional[int] = None


class CampusDriveCreateResponse(BaseModel):
    drive_id: UUID
    message: str
    start_date: datetime
    end_date: datetime
    target_batch: dict[str, Any]
