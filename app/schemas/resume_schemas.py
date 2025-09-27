from pydantic import BaseModel
from uuid import UUID
from typing import Optional, List, Dict
from enum import Enum
from datetime import datetime
from fastapi import Form


class ResumeTypeEnum(str, Enum):
    Uploaded = "Uploaded"
    Uplifted = "Uplifted"


class ResumeUploadInput(BaseModel):
    user_id: UUID
    resume_type: ResumeTypeEnum
    template_id: Optional[UUID] = None
    source_resume_id: Optional[UUID] = None

    @classmethod
    def as_form(
        cls,
        student_id: UUID = Form(...),
        resume_type: ResumeTypeEnum = Form(...),
        template_id: Optional[UUID] = Form(None),
        source_resume_id: Optional[UUID] = Form(None),
    ):
        return cls(
            student_id=student_id,
            resume_type=resume_type,
            template_id=template_id,
            source_resume_id=source_resume_id,
        )


class ResumeUploadResponse(BaseModel):
    version_id: UUID
    student_id: UUID
    resume_type: ResumeTypeEnum
    template_id: Optional[UUID]
    source_resume_id: Optional[UUID]
    file_path: str
    created_at: datetime

    class Config:
        from_attributes = True


class ResumeVersionResponse(BaseModel):
    version_id: UUID
    student_id: UUID
    resume_type: ResumeTypeEnum
    resume_name: Optional[str]
    source_resume_id: Optional[UUID]
    file_path: Optional[str]
    ats_score: Optional[float]
    ai_feedback: Optional[str]
    created_at: datetime
    is_active: bool

    class Config:
        from_attributes = True


class Education(BaseModel):
    degree: str
    institution: str
    dates: str
    details: List[str]


class Experience(BaseModel):
    role: str
    company: str
    dates: str
    details: List[str]


class Project(BaseModel):
    title: str
    dates: str
    details: List[str]


class Certification(BaseModel):
    certification_name: str
    issued_by: str
    issue_date: Optional[str]
    expiration_date: Optional[str]


class ExtraFields(BaseModel):
    certifications: List[Certification]
    languages: List[str]
    courses: List[str]


class ResumeData(BaseModel):
    name: str
    phone: str
    email: str
    linkedin: str
    github: str
    objective: str
    education: List[Education]
    experience: List[Experience]
    projects: List[Project]
    skills: Dict[str, List[str]]
    achievements: List[str]
    publications: List[str]
    extra_fields: ExtraFields
    valid_descriptions: bool
    resume_improvements: str
    project_clarity: bool


class PersonalInfo(BaseModel):
    firstName: str
    lastName: str
    title: str
    summary: str
    email: str
    phone: str
    location: str
    website: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None


class WorkExperience(BaseModel):
    id: str
    company: str
    position: str
    startDate: str
    endDate: str
    current: bool
    description: str
    achievements: List[str]
    location: Optional[str] = None


class Education(BaseModel):
    id: str
    institution: str
    degree: str
    field: str
    startDate: str
    endDate: str
    current: bool
    description: str
    gpa: Optional[str] = None
    location: Optional[str] = None


class Project(BaseModel):
    id: str
    title: str
    description: str
    startDate: str
    endDate: str
    current: bool
    link: Optional[str] = None
    technologies: List[str]


class Skill_Resume(BaseModel):
    id: str
    name: str
    level: int  # 1-5


class Language(BaseModel):
    id: str
    name: str
    proficiency: str  # e.g. "Fluent"


class Certification(BaseModel):
    id: str
    name: str
    organization: str
    date: str
    expiration: Optional[str] = None
    credentialId: Optional[str] = None


class ResumeDataBuilder(BaseModel):
    personalInfo: PersonalInfo
    workExperience: List[WorkExperience]
    education: List[Education]
    projects: List[Project]
    skills: List[Skill_Resume]
    languages: List[Language]
    certifications: List[Certification]
class ResumeSummary(BaseModel):
    skills: str
    degree_qualification: str
    college_name: str
    branch: str
    start_year: Optional[int]
    passed_out_year: Optional[int]
    location: Optional[str] = None  
    grade: Optional[float]
