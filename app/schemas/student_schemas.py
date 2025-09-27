from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime
from typing import Any, Dict, Optional, List, Union
from datetime import date


class StudentBase(BaseModel):
    email: EmailStr
    aspirations: List[str]  # List of aspiration texts


class StudentCreate(StudentBase):
    user_id: UUID


class StudentUpdate(BaseModel):
    email: Optional[EmailStr]
    aspiration: Optional[str]


class AspirationResponse(BaseModel):
    aspiration_id: UUID
    aspiration_text: str

    model_config = {"from_attributes": True}


class StudentResponse(BaseModel):
    student_id: UUID
    user_id: UUID
    email: EmailStr
    aspirations: List[
        AspirationResponse
    ]  # ✅ Corrected: matches SQLAlchemy relationship
    created_at: datetime

    model_config = {"from_attributes": True}


# Models for related tables
class WorkExperienceUpdateSchema(BaseModel):
    id: Optional[UUID] = None
    position_title: Optional[str] = None
    company_name: Optional[str] = None
    duration: Optional[str] = None
    description: Optional[str] = None


class CompanyExperienceUpdateSchema(BaseModel):
    id: Optional[UUID] = None
    company_name: Optional[str] = None
    your_position: Optional[str] = None
    dates: Optional[str] = None
    company_website: Optional[str] = None
    company_location: Optional[str] = None
    company_description: Optional[str] = None
    company_logo: Optional[str] = None
    work_experiences: Optional[List[WorkExperienceUpdateSchema]] = None


class SkillUpdateSchema(BaseModel):
    programming_languages: Optional[List[str]] = None
    tools_technologies: Optional[List[str]] = None
    soft_skills: Optional[List[str]] = None
    relevant_courses: Optional[List[str]] = None


class CertificationUpdateSchema(BaseModel):
    id: Optional[UUID] = None
    certification_name: Optional[str] = None
    issued_by: Optional[str] = None
    issue_date: Optional[date] = None
    expiration_date: Optional[date] = None


class SocialProfileUpdateSchema(BaseModel):
    id: Optional[UUID] = None
    website: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    twitter: Optional[str] = None


class EducationUpdateSchema(BaseModel):
    id: Optional[UUID] = None
    institution_name: Optional[str] = None
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    grade: Optional[str] = None
    description: Optional[str] = None


class LanguageUpdateSchema(BaseModel):
    id: Optional[UUID] = None
    language_name: Optional[str] = None
    proficiency_level: Optional[str] = None


class ProjectUpdateSchema(BaseModel):
    id: Optional[UUID] = None
    title: Optional[str] = None
    dates: Optional[str] = None
    details: Optional[Union[str, List[str]]] = (
        None  # Allow either string or list of strings
    )


# Main request model with all fields optional
class StudentUpdateSchema(BaseModel):
    # Personal info fields
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    bio: Optional[str] = None
    profile_img_path: Optional[str] = None

    # Related tables
    experience: Optional[List[CompanyExperienceUpdateSchema]] = None
    skills: Optional[SkillUpdateSchema] = None
    certifications: Optional[List[CertificationUpdateSchema]] = None
    social_profiles: Optional[SocialProfileUpdateSchema] = None
    education: Optional[List[EducationUpdateSchema]] = None
    languages: Optional[List[LanguageUpdateSchema]] = None
    projects: Optional[List[ProjectUpdateSchema]] = None
    student_id: Optional[UUID] = None
    achievements: Optional[List[str]] = None

    # Social profile fields directly at top level
    personal_website: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    twitter: Optional[str] = None
    website: Optional[str] = None

    # Extra fields containing certifications and languages
    extra_fields: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True
