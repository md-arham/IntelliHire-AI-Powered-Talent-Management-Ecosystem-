from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, or_, desc, asc
from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import List, Optional
import uuid
import logging

from app.schemas.companies_schemas import (
    CompanyCreate,
    CompanyOut,
    CompanyUpdate,
    CompanyListResponse,
    BulkCompanyResponse,
    SearchResponse,
)
from app.database.db import get_db
from app.database.models import Company

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/company", tags=["Company"])


@router.post(
    "/companies/", response_model=CompanyOut, status_code=status.HTTP_201_CREATED
)
async def create_company(company: CompanyCreate, db: AsyncSession = Depends(get_db)):
    """
    Create a new company with proper error handling and validation.

    Args:
        company (CompanyCreate): Data for the company to create.
        db (AsyncSession): Asynchronous database session.

    Returns:
        CompanyOut: The created company object.

    Raises:
        HTTPException: If the company already exists or creation fails.
    """
    try:
        # Check if company with same name already exists (if applicable)
        existing_stmt = select(Company).where(Company.name == company.name)
        existing_result = await db.execute(existing_stmt)
        if existing_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Company with this name already exists",
            )

        db_company = Company(**company.model_dump())
        db.add(db_company)
        await db.commit()
        await db.refresh(db_company)

        logger.info(f"Created company with ID: {db_company.company_id}")
        return db_company

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating company: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create company",
        )


@router.get("/companies/", response_model=CompanyListResponse)
async def read_companies(
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(
        default=10, ge=1, le=100, description="Number of records to return"
    ),
    name: Optional[str] = Query(
        default=None, description="Filter by company name (partial match)"
    ),
    sort_by: Optional[str] = Query(default="name", description="Field to sort by"),
    sort_order: Optional[str] = Query(
        default="asc", regex="^(asc|desc)$", description="Sort order"
    ),
    db: AsyncSession = Depends(get_db),
    ):
    """
    Retrieve a list of companies with filtering, sorting, and pagination.

    Args:
        skip (int): Number of records to skip.
        limit (int): Number of records to return.
        name (Optional[str]): Filter by company name (partial match).
        sort_by (Optional[str]): Field to sort by.
        sort_order (Optional[str]): Sort order ('asc' or 'desc').
        db (AsyncSession): Asynchronous database session.

    Returns:
        CompanyListResponse: List of companies matching the criteria.

    Raises:
        HTTPException: If fetching companies fails.
    """
    try:
        # Build base query
        stmt = select(Company)

        # Apply filters
        conditions = []
        if name:
            conditions.append(Company.name.ilike(f"%{name}%"))

        if conditions:
            stmt = stmt.where(and_(*conditions))

        # Apply sorting
        if hasattr(Company, sort_by):
            sort_column = getattr(Company, sort_by)
            if sort_order == "desc":
                stmt = stmt.order_by(desc(sort_column))
            else:
                stmt = stmt.order_by(asc(sort_column))

        # Apply pagination
        stmt = stmt.offset(skip).limit(limit)

        # Execute query
        result = await db.execute(stmt)
        companies = result.scalars().all()

        return CompanyListResponse(
            data=companies,
        )

    except Exception as e:
        logger.error(f"Error fetching companies: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch companies",
        )


@router.get("/companies/{company_id}", response_model=CompanyOut)
async def read_company(company_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Retrieve a specific company by its UUID.

    Args:
        company_id (uuid.UUID): UUID of the company to retrieve.
        db (AsyncSession): Asynchronous database session.

    Returns:
        CompanyOut: The company object.

    Raises:
        HTTPException: If the company is not found or fetching fails.
    """
    try:
        stmt = select(Company).where(Company.company_id == company_id)
        result = await db.execute(stmt)
        company = result.scalar_one_or_none()

        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Company with ID {company_id} not found",
            )
        return company

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching company {company_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch company",
        )


@router.put("/companies/{company_id}", response_model=CompanyOut)
async def update_company(
    company_id: uuid.UUID,
    updated_data: CompanyUpdate,
    db: AsyncSession = Depends(get_db),
    ):
    """
    Update a company with validation and conflict checking.

    Args:
        company_id (uuid.UUID): UUID of the company to update.
        updated_data (CompanyUpdate): Fields to update.
        db (AsyncSession): Asynchronous database session.

    Returns:
        CompanyOut: The updated company object.

    Raises:
        HTTPException: If the company is not found, no fields are provided, 
                       there is a name conflict, or update fails.
    """
    try:
        # Check if company exists
        stmt = select(Company).where(Company.company_id == company_id)
        result = await db.execute(stmt)
        company = result.scalar_one_or_none()

        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Company with ID {company_id} not found",
            )

        # Get only the fields that are being updated
        update_data = updated_data.model_dump(exclude_unset=True)

        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields provided for update",
            )

        # Check for name conflicts if name is being updated
        if "name" in update_data and update_data["name"] != company.name:
            existing_stmt = select(Company).where(
                and_(
                    Company.name == update_data["name"],
                    Company.company_id != company_id,
                )
            )
            existing_result = await db.execute(existing_stmt)
            if existing_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Company with this name already exists",
                )

        # Apply updates
        for key, value in update_data.items():
            setattr(company, key, value)

        await db.commit()
        await db.refresh(company)

        logger.info(f"Updated company with ID: {company_id}")
        return company

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating company {company_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update company",
        )


@router.delete("/companies/{company_id}", status_code=status.HTTP_200_OK)
async def delete_company(company_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Delete a company by its UUID with validation.

    Args:
        company_id (uuid.UUID): UUID of the company to delete.
        db (AsyncSession): Asynchronous database session.

    Returns:
        dict: Confirmation message and deleted company ID.

    Raises:
        HTTPException: If the company is not found or deletion fails.
    """
    try:
        stmt = select(Company).where(Company.company_id == company_id)
        result = await db.execute(stmt)
        company = result.scalar_one_or_none()

        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Company with ID {company_id} not found",
            )

        await db.delete(company)
        await db.commit()

        logger.info(f"Deleted company with ID: {company_id}")
        return {
            "message": "Company deleted successfully",
            "company_id": str(company_id),
        }

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting company {company_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete company",
        )


# Bulk operations for better performance
@router.post("/companies/bulk", response_model=BulkCompanyResponse)
async def create_companies_bulk(
    companies: List[CompanyCreate], db: AsyncSession = Depends(get_db)
    ):
    """
    Create multiple companies in a single transaction.

    Args:
        companies (List[CompanyCreate]): List of companies to create.
        db (AsyncSession): Asynchronous database session.

    Returns:
        BulkCompanyResponse: Result message, created count, and created companies.

    Raises:
        HTTPException: If more than 100 companies are provided or bulk creation fails.
    """
    if len(companies) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create more than 100 companies at once",
        )

    try:
        db_companies = [Company(**company.model_dump()) for company in companies]
        db.add_all(db_companies)
        await db.commit()

        # Refresh all created companies
        for company in db_companies:
            await db.refresh(company)

        logger.info(f"Created {len(db_companies)} companies in bulk")
        return BulkCompanyResponse(
            message=f"Successfully created {len(db_companies)} companies",
            created_count=len(db_companies),
            companies=db_companies,
        )

    except Exception as e:
        await db.rollback()
        logger.error(f"Error in bulk company creation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create companies in bulk",
        )


@router.get("/companies/search/", response_model=SearchResponse)
async def search_companies(
    query: str = Query(..., min_length=2, description="Search query"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    ):
    """
    Search for companies across multiple fields.

    Args:
        query (str): Search query string.
        skip (int): Number of records to skip.
        limit (int): Number of records to return.
        db (AsyncSession): Asynchronous database session.

    Returns:
        SearchResponse: Search results, including total and returned counts.

    Raises:
        HTTPException: If the search operation fails.
    """
    try:
        # Search across multiple fields
        search_conditions = or_(
            Company.name.ilike(f"%{query}%"),
            # Add other searchable fields as needed
            # Company.description.ilike(f"%{query}%"),
            # Company.industry.ilike(f"%{query}%"),
        )

        stmt = select(Company).where(search_conditions)

        # Get total count
        count_result = await db.execute(stmt)
        total_count = len(count_result.scalars().all())

        # Apply pagination and ordering
        stmt = stmt.order_by(Company.name).offset(skip).limit(limit)
        result = await db.execute(stmt)
        companies = result.scalars().all()

        return SearchResponse(
            data=companies,
            query=query,
            total_count=total_count,
            returned_count=len(companies),
        )

    except Exception as e:
        logger.error(f"Error in company search: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search operation failed",
        )
