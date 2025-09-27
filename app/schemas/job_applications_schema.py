from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel
from app.database.models.enums_models import JobApplicationStatus

class JobApplicationCreate(BaseModel):
    application_id: UUID
    job_id: UUID
    student_id: UUID
    resume_version_id: UUID
    status: JobApplicationStatus = JobApplicationStatus.InProgress
    current_stage: Optional[str] = None
    fitment_score: Optional[float] = None
    # Exclude applied_on and last_updated, let database handle them
    # applied_on and last_updated are managed by server_default and onupdate in the model

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True

class JobApplicationRead(BaseModel):
    application_id: UUID
    job_id: UUID
    student_id: UUID
    # resume_version_id: UUID
    status: JobApplicationStatus
    applied_on: datetime
    current_stage: Optional[str]
    fitment_score: Optional[float]
    last_updated: datetime
    # job_title: str | None
    # company_name: str | None

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True