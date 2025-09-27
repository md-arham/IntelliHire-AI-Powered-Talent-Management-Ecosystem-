from pydantic import BaseModel, Field, constr, conint, UUID4, HttpUrl
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from fastapi import UploadFile
from enum import Enum


# ------------------- Hackathon Schemas -------------------
class HackathonBase(BaseModel):
    name: constr(min_length=3, max_length=500) = Field(
        ..., description="Title of the hackathon"
    )
    description: Optional[str] = Field(None, description="Short summary or overview")
    start_date: datetime = Field(..., description="When the hackathon begins")
    end_date: datetime = Field(..., description="When the hackathon ends")
    registration_deadline: datetime = Field(..., description="Last date to register")
    mode: str = Field(..., description="Format of participation: Online or Offline")
    theme: Optional[str] = Field(None, description="Theme of the hackathon")
    eligibility_criteria: Optional[str] = Field(None, description="Who can participate")
    min_team_size: conint(ge=1) = Field(
        ..., description="Minimum number of team members"
    )
    max_team_size: conint(ge=1) = Field(
        ..., description="Maximum number of team members"
    )
    submission_guidelines: Optional[str] = Field(
        None, description="Instructions for submitting projects"
    )
    rules: Optional[List[str]] = Field(None, description="List of rules to be followed")
    timeline: Optional[str] = Field(
        None, description="Timeline in JSON or descriptive string"
    )
    status: Optional[str] = Field(
        default="Upcoming", description="Status like Upcoming, Ongoing, Ended"
    )
    image: Optional[str] = Field(None, description="Image filename or URL")
    featured: Optional[bool] = Field(
        default=False, description="Mark as featured event"
    )
    prizes: Optional[List[str]] = Field(None, description="List of prizes")
    sponsoredBy: Optional[List[str]] = Field(default=None, description="")
    user_id: UUID = Field(..., description="The ID of the user creating the hackathon")

    location: str = Field(..., description="Location or city")

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class HackathonCreate(HackathonBase):
    pass


class HackathonInResponse(HackathonBase):
    id: UUID
    user_id: UUID
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ------------------- Problem Statement Schemas -------------------
class ProblemStatementBase(BaseModel):
    title: constr(min_length=5, max_length=500) = Field(
        ..., description="Problem title"
    )
    description: str = Field(..., description="Detailed problem description")


class ProblemStatementCreate(ProblemStatementBase):
    hackathon_id: UUID = Field(
        ..., description="Hackathon ID for which this problem is created"
    )


class ProblemStatementInResponse(ProblemStatementBase):
    id: UUID
    hackathon_id: UUID

    model_config = {"from_attributes": True}


class ProblemStatementUpdate(BaseModel):
    title: Optional[constr(min_length=5, max_length=150)] = None
    description: Optional[str] = None


# ------------------- Hackathon registration schemas ---------------
class HackathonRegistrationCreate(BaseModel):
    team_id: UUID4
    hackathon_id: UUID4
    agreed_to_eligibility: bool

    model_config = {"from_attributes": True}


class HackathonRegistrationResponse(BaseModel):
    message: str
    team_id: UUID4
    team_name: str
    hackathon_id: UUID4
    agreed_to_eligibility: bool

    model_config = {"from_attributes": True}


# -------------team schemas--------------


class TeamCreate(BaseModel):
    team_name: str
    members: List[UUID4]  # List of student UUIDs

    model_config = {"from_attributes": True}


class TeamResponse(BaseModel):
    team_id: UUID4
    team_name: str
    created_at: datetime
    members: List[UUID4]
    registrations: List[HackathonRegistrationResponse]

    model_config = {"from_attributes": True}


class TeamStudentCreate(BaseModel):
    team_id: UUID4
    student_ids: List[UUID4]  # ← changed from single student_id


class TeamStudentResponse(BaseModel):
    team_id: UUID
    student_id: UUID
    student_name: Optional[str] = None

    model_config = {"from_attributes": True}


class TeamWithRegistrationCreate(BaseModel):
    team_name: str
    members: List[UUID]
    hackathon_id: UUID
    agreed_to_eligibility: bool


# ----------submission-----------------


class SubmissionCreate(BaseModel):
    submission_type: Optional[str] = None
    file: Optional[UploadFile] = None
    url: Optional[HttpUrl] = None
    github_url: Optional[str] = None
    problem_statement_id: UUID
    hackathon_id: UUID
    team_id: UUID


class SubmissionOut(BaseModel):
    id: UUID
    submission_type: str
    submission_value: str
    team_id: UUID
    hackathon_id: UUID
    problem_statement_id: UUID

    class Config:
        from_attributes = True


# -------------scoring--------


class ScoringBase(BaseModel):
    hackathon_id: UUID
    problem_statement_id: UUID
    team_id: UUID
    submission_id: UUID
    score: float


class ScoringCreate(ScoringBase):
    pass


class ScoringUpdate(BaseModel):
    score: float


class ScoringOut(ScoringBase):
    id: UUID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# -----------filter-----------------


class HackathonStatusEnum(str, Enum):
    upcoming = "upcoming"
    active = "active"
    completed = "completed"


class DateRangeFilter(BaseModel):
    start_date: datetime
    end_date: datetime
