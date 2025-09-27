from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID

from app.database.db import get_db  # Async DB
from app.schemas.colleges_schemas import CollegeCreate, CollegeUpdate, CollegeOut
import app.services.colleges_services as colleges_service
from app.api.deps import get_current_user
from app.schemas.auth_schemas import TokenData

router = APIRouter(prefix="/api/colleges", tags=["Colleges"])


@router.get("/", response_model=List[CollegeOut])
async def read_colleges(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    token_data: TokenData = Depends(get_current_user),
):
    """
    Retrieve a list of colleges with pagination support.

    Args:
        skip (int): Number of records to skip for pagination.
        limit (int): Maximum number of records to return.
        db (AsyncSession): Asynchronous database session dependency.

    Returns:
        List[CollegeOut]: List of college objects.
    """
    colleges = await colleges_service.get_colleges(db, skip=skip, limit=limit)
    return colleges


@router.get("/{college_id}", response_model=CollegeOut)
async def read_college(
    college_id: UUID,
    db: AsyncSession = Depends(get_db),
    token_data: TokenData = Depends(get_current_user),
):
    """
    Retrieve a single college by its ID.

    Args:
        college_id (UUID): Unique identifier of the college.
        db (AsyncSession): Asynchronous database session dependency.

    Returns:
        CollegeOut: College data.

    Raises:
        HTTPException: If the college is not found.
    """
    college = await colleges_service.get_college(db, college_id)
    if not college:
        raise HTTPException(status_code=404, detail="College not found")
    return college


@router.post("/", response_model=CollegeOut, status_code=status.HTTP_201_CREATED)
async def create_college(
    college_in: CollegeCreate,
    db: AsyncSession = Depends(get_db),
    token_data: TokenData = Depends(get_current_user),
):
    """
    Create a new college record.

    Args:
        college_in (CollegeCreate): College creation schema.
        db (AsyncSession): Asynchronous database session dependency.

    Returns:
        CollegeOut: Created college data.
    """
    college = await colleges_service.create_college(db, college_in)
    return college


@router.put("/{college_id}", response_model=CollegeOut)
async def update_college(
    college_id: UUID,
    college_in: CollegeUpdate,
    db: AsyncSession = Depends(get_db),
    token_data: TokenData = Depends(get_current_user),
):
    """
    Update an existing college's information.

    Args:
        college_id (UUID): Unique identifier of the college.
        college_in (CollegeUpdate): Updated college data.
        db (AsyncSession): Asynchronous database session dependency.

    Returns:
        CollegeOut: Updated college data.

    Raises:
        HTTPException: If the college is not found.
    """
    updated_college = await colleges_service.update_college(db, college_id, college_in)
    if not updated_college:
        raise HTTPException(status_code=404, detail="College not found")
    return updated_college


@router.delete("/{college_id}", response_model=CollegeOut)
async def delete_college(
    college_id: UUID,
    db: AsyncSession = Depends(get_db),
    token_data: TokenData = Depends(get_current_user),
):
    """
    Delete a college by its ID.

    Args:
        college_id (UUID): Unique identifier of the college.
        db (AsyncSession): Asynchronous database session dependency.

    Returns:
        CollegeOut: Deleted college data.

    Raises:
        HTTPException: If the college is not found.
    """
    deleted = await colleges_service.delete_college(db, college_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="College not found")
    return deleted
