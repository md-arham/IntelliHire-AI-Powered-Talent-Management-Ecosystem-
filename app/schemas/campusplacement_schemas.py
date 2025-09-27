from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from pydantic import EmailStr, Field


class StudentWithApplicationsResponse(BaseModel):
    student_id: UUID
    email: str
    full_name: Optional[str]
    profile_img_path: Optional[str]
    batch_year: int
    department: Optional[str]
    section: Optional[str]
    applied_companies: List[str]

    class Config:
        from_attributes = True


class PlacementResourceCreate(BaseModel):
    title: str
    description: Optional[str] = None


class PlacementResourceResponse(BaseModel):
    resource_id: UUID
    title: str
    description: Optional[str]
    file_path: str
    created_at: datetime

    class Config:
        from_attributes = True


class JobBase(BaseModel):
    job_id: UUID
    title: str
    company_name: Optional[str]
    location: Optional[str]
    posted_at: datetime

    class Config:
        from_attributes = True


class RecommendJobRequest(BaseModel):
    job_id: UUID
    batch_year: int


class StudentRegistrationCollegeID(BaseModel):
    full_name: str = Field(..., min_length=3)
    email: EmailStr
    password: str = Field(..., min_length=8)
    college_id: UUID
    aspirations: List[str]
    batch: Optional[int] = None
    branch: Optional[str] = None

