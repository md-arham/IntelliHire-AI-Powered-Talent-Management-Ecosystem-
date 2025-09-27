from pydantic import BaseModel, EmailStr, HttpUrl
from uuid import UUID
from datetime import datetime
from typing import Optional,List
from enum import Enum
from app.schemas.auth_schemas import UserRole

# class UserRole(str, Enum):
#     student = "Student"
#     employer = "Employer"
#     admin = "Admin"


class CompanyType(str, Enum):
    Startup = "Startup"
    Midsize = "Midsize"
    MNC = "MNC"


class EmployerProfileInput(BaseModel):
    company_name: str
    company_type: CompanyType
    company_description: Optional[str] = None
    logo_url: Optional[HttpUrl] = None
    website_url: Optional[HttpUrl] = None


class StudentProfileInput(BaseModel):
    email: EmailStr
    aspiration: str


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str]
    role: Optional[UserRole]

class UserWithPassword(UserBase):
    password: str # shared for creation or login input
    

class UserCreate(UserBase):
    password: str  # plain text; will be hashed before storing

    # Optional because we decide based on role
    employer_profile: Optional[EmployerProfileInput] = None
    student_profile: Optional[StudentProfileInput] = None


class UserUpdate(BaseModel):
    full_name: Optional[str]
    role: Optional[UserRole]

    # Employer-specific optional fields
    company_name: Optional[str]
    company_type: Optional[CompanyType]
    company_description: Optional[str]
    logo_url: Optional[HttpUrl]
    website_url: Optional[HttpUrl]

    model_config = {"from_attributes": True}


class UserResponse(UserBase):
    user_id: UUID
    created_at: Optional[datetime]

    model_config = {
        "from_attributes": True
    }

# class UserResponsewithActivity(UserResponse):
#     is_active: bool
#     is_superuser: bool
    
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ProfileUpdateSchema(BaseModel):
    name: Optional[str]
    email: Optional[EmailStr]
    phone: Optional[str]
    location: Optional[str]
    university: Optional[str]
    major: Optional[str]
    graduationYear: Optional[
        str
    ]  # We'll handle the string format in the update function
    company: Optional[str]
    position: Optional[str]
    website: Optional[str]
    linkedin: Optional[str]
    github: Optional[str]
    twitter: Optional[str]
    bio: Optional[str]
    skills: Optional[List[str]]