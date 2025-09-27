import uuid
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

# Import the Enum from the models to ensure consistency
from app.database.models.job_postings_models import (
    JobOriginType,
    JobCategoryType,
)

from app.database.models.enums_models import InternshipType, JobType


class JobPostingBase(BaseModel):
    employer_id: uuid.UUID
    company_name: Optional[str] = Field(None, description="Name of the hiring company")
    title: str = Field(..., max_length=150, description="The title of the job posting")
    description: Optional[str] = Field(
        None, description="Detailed description of the job"
    )
    location: Optional[str] = Field(None, max_length=100, description="Job location")

    job_type: Optional[JobType] = Field(None, description="Job type as defined in enum")
    internship_type: Optional[InternshipType] = Field(None, description="Work type as defined in enum")
    category: Optional[str] = Field(None, max_length=100, description="Job category")
    role: Optional[str] = Field(None, max_length=100, description="Job role")
    required_skills: Optional[List[str]] = Field(
        None, description="List of required skills"
    )
    min_experience: Optional[str] = Field(
        None,
        description="Minimum years of experience required (0 for entry-level)",
    )
    salary_range: Optional[str] = Field(None, description="Salary range indication")
    application_deadline: Optional[date] = Field(
        None, description="Application deadline"
    )
    additional_info: Optional[Dict[str, Any]] = Field(
        None, description="Additional structured info"
    )
    is_active: bool = Field(
        default=True, description="Whether the job posting is currently active"
    )


class JobPostingCreate(JobPostingBase):
    job_origin: JobOriginType = Field(
        ..., description="Origin of the Job Post (internal or external)"
    )
    job_category_type: JobCategoryType = Field(
        ..., description="Whether the post is a job or internship"
    )


class JobDescriptionInput(BaseModel):
    title: str = Field(..., description="The job title.")
    category: Optional[str] = Field(
        None, description="Optional job category (e.g., Engineering, Marketing)."
    )
    role: Optional[str] = Field(
        None, description="Optional specific role (e.g., Backend Developer)."
    )
    responsibilities: str = Field(
        ...,
        description="Key responsibilities for the role (can be a paragraph or bullet points).",
    )
    requirements: str = Field(
        ...,
        description="Required skills and qualifications (can be a paragraph or bullet points).",
    )


class JobDescriptionOutput(BaseModel):
    description: str = Field(..., description="The generated job description.")


class JobPostingRead(JobPostingBase):
    employer_id: Optional[uuid.UUID] = None
    job_id: uuid.UUID
    posted_at: datetime

    # Optional overrides
    title: Optional[str] = None
    job_type: Optional[JobType] = None
    is_active: Optional[bool] = None
    isSaved: Optional[bool] = Field(
        None, description="Whether the job is bookmarked by the student"
    )
    bookmark_id: Optional[uuid.UUID] = Field(
        None, description="ID of the bookmark if the job is bookmarked"
    )

    model_config = ConfigDict(from_attributes=True)


class JobPostingFilterRequest(BaseModel):
    user_id: Optional[uuid.UUID] = None
    job_origin: Optional[JobOriginType] = JobOriginType.EXTERNAL
    job_category_type: Optional[JobCategoryType] = JobCategoryType.INTERNSHIP
    is_remote: Optional[bool] = Field(None, description="Filter by remote job status")
    location: Optional[str] = Field(
        None, description="Filter by job location (e.g., 'New York', 'Remote')"
    )

    job_type: Optional[JobType] = Field(None, description="Filter by job type")

    category: Optional[str] = Field(
        None, description="Filter by job category (e.g., Software Engineering)"
    )
    title: Optional[str] = Field(
        None, description="Filter by job title (e.g., Backend Developer)"
    )
    page: int = 1
    page_size: int = 10


# Schema for creating a bookmark
class BookmarkCreate(BaseModel):
    job_id: uuid.UUID = Field(..., description="ID of the job posting to bookmark")
    user_id: uuid.UUID = Field(
        ..., description="ID of the student bookmarking the job (maps to student_id)"
    )


class BookmarkRead(BaseModel):
    bookmark_id: uuid.UUID = Field(..., description="Unique ID of the bookmark")
    job_id: uuid.UUID = Field(..., description="ID of the bookmarked job posting")
    student_id: uuid.UUID = Field(
        ..., description="ID of the student who bookmarked the job"
    )
    job_title: Optional[str] = Field(None, description="Title of the bookmarked job")
    company_name: Optional[str] = Field(
        None, description="Name of the company posting the job"
    )
    job_location: Optional[str] = Field(None, description="Location of the job")
    job_type: Optional[JobType] = Field(None, description="Type of the job")
    posted_at: Optional[datetime] = Field(None, description="When the job was posted")

    model_config = ConfigDict(from_attributes=True)


class PaginatedInternshipResponse(BaseModel):
    items: List[JobPostingRead]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_more: bool