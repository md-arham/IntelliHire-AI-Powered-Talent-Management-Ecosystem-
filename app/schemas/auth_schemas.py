from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from uuid import UUID
from enum import Enum
from typing import Optional, List, Literal, Annotated, Union
from fastapi import Body


class AuthProviderEnum(str, Enum):
    GOOGLE = "google"
    LINKEDIN = "linkedin"


class LinkedAuthResponse(BaseModel):
    user_id: UUID
    email: EmailStr
    full_name: str
    role: str



class UserRole(str, Enum):
    student = "student"
    campus_officer = "campus_officer"
    employer = "employer"
    superadmin = "superadmin"

class BaseUserRegister(BaseModel):
    full_name: str
    email: EmailStr
    password: str = Field(min_length=6)
    role: UserRole


class StudentRegister(BaseUserRegister):
    role: Literal[UserRole.student] = UserRole.student  
    college_id: UUID
    batch_year: int
    department: Optional[str] = None
    section: Optional[str] = None
    aspirations: Optional[List[str]] = []

class CampusOfficerRegister(BaseUserRegister):
    role: Literal[UserRole.campus_officer] = UserRole.campus_officer
    college_id: UUID
    contact_detail: Optional[str]

class EmployerRegister(BaseUserRegister):
    role: Literal[UserRole.employer] = UserRole.employer
    company_id: UUID

class SuperAdminRegister(BaseUserRegister):
    role: Literal[UserRole.superadmin] = UserRole.superadmin


UserRegistrationUnion = Annotated[
    Union[CampusOfficerRegister, StudentRegister, EmployerRegister, SuperAdminRegister],
    Body(
        discriminator="role",
        examples={
            "student": {
                "summary": "Register a Student",
                "value": {
                    "role": "student",
                    "full_name": "Alice Student",
                    "email": "alice@student.edu",
                    "password": "securepass",
                    "college_id": "uuid-here",
                    "batch_year": 2025,
                    "department": "CSE",
                    "section": "A",
                    "aspirations": ["ML Engineer"],
                },
            },
            "campus_officer": {
                "summary": "Register a Campus Officer",
                "value": {
                    "role": "campus_officer",
                    "full_name": "Bob Officer",
                    "email": "bob@college.edu",
                    "password": "strongpass",
                    "college_id": "uuid-here",
                    "contact_detail": "9876543210",
                },
            },
            "employer": {
                "summary": "Register an Employer",
                "value": {
                    "role": "employer",
                    "full_name": "Eve Employer",
                    "email": "eve@company.com",
                    "password": "topsecret",
                    "company_id": "uuid-here",
                },
            },
        },
    ),
]


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    user_id: UUID
    full_name: str
    role: UserRole
    email: str


# schemas/student_registration.py


class StudentRegistrationCollegeID(BaseModel):
    full_name: str = Field(..., min_length=3)
    email: EmailStr
    password: str = Field(..., min_length=8)
    college_id: UUID
    aspirations: List[str]


class StudentDetails(BaseModel):
    student_id: UUID
    user_id: UUID
    college_id: UUID
    email: str
    full_name: str  # from User model (joined)
    aspirations: Optional[List[str]] = []

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    username: Optional[str] = None
    user_id: Optional[str] = None


class LoginRequestRBAC(BaseModel):
    email: str
    password: str


class EmailRequest(BaseModel):
    email: str

class OTPRequest(BaseModel):
    otp: str


class LoginOutput(BaseModel):
    message: str
    access_token: str
    token_type: str
    email: str
    role: str
