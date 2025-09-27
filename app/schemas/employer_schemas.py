from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional
from app.database.models.enums_models import CompanyType
from app.schemas.user_schemas import UserResponse  # assuming it exists


class EmployerBase(BaseModel):
    company_name: Optional[str]
    company_type: Optional[CompanyType]
    company_description: Optional[str]
    logo_url: Optional[str]
    website_url: Optional[str]


class EmployerFilterParams(BaseModel):
    company_type: Optional[CompanyType] = None


class UserUpdateSchema(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None


class CompanyUpdateSchema(BaseModel):
    name: Optional[str] = None
    type: Optional[CompanyType] = None
    description: Optional[str] = None
    location: Optional[str] = None
    logo_url: Optional[str] = None
    website_url: Optional[str] = None


class EmployerUpdateSchema(BaseModel):
    # Keep backward compatibility with flat structure
    company_name: Optional[str] = None
    company_type: Optional[CompanyType] = None
    company_description: Optional[str] = None
    logo_url: Optional[str] = None
    website_url: Optional[str] = None
    user: Optional[UserUpdateSchema] = None

    # Optional: Add nested company structure for future use
    company: Optional[CompanyUpdateSchema] = None


class CompanyResponse(BaseModel):
    company_id: UUID
    name: str
    type: Optional[CompanyType]
    location: Optional[str]
    logo_url: Optional[str]
    website_url: Optional[str]
    description: Optional[str]

    model_config = {"from_attributes": True}


class EmployerResponse(BaseModel):
    employer_id: UUID
    user_id: UUID
    company_id: Optional[UUID]
    created_at: datetime
    user: UserResponse
    company: Optional[CompanyResponse]  # Add company relationship

    model_config = {"from_attributes": True}


class ExportApplicantsRequest(BaseModel):
    job_id: UUID
