from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from app.database.models.enums_models import CompanyType


class CompanyBase(BaseModel):
    name: str
    type: Optional[CompanyType]
    location: Optional[str]
    description: Optional[str]
    logo_url: Optional[str]
    website_url: Optional[str]


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(CompanyBase):
    pass


class CompanyOut(CompanyBase):
    company_id: UUID

    class Config:
        from_attributes = True


class PaginationInfo(BaseModel):
    total_count: int
    total_pages: int
    current_page: int
    page_size: int
    has_next: bool
    has_previous: bool


class FilterInfo(BaseModel):
    name: Optional[str] = None
    sort_by: str = "name"
    sort_order: str = "asc"


class CompanyListResponse(BaseModel):
    data: list[CompanyOut]


class BulkCompanyResponse(BaseModel):
    message: str
    created_count: int
    companies: list[CompanyOut]


class SearchResponse(BaseModel):
    data: list[CompanyOut]
    query: str
    total_count: int
    returned_count: int
