from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from uuid import UUID
from typing import Optional

from app.database.models.campusplacement_models import College


async def get_college(db: AsyncSession, college_id: UUID) -> Optional[College]:
    """
    Retrieve a college by its UUID.

    Args:
        db (AsyncSession): Asynchronous database session.
        college_id (UUID): The college's UUID.

    Returns:
        Optional[College]: The College instance or None if not found.
    """
    result = await db.execute(select(College).where(College.college_id == college_id))
    return result.scalars().first()


async def get_colleges(db: AsyncSession, skip: int = 0, limit: int = 100):
    """
    Retrieve a list of colleges with pagination.

    Args:
        db (AsyncSession): Asynchronous database session.
        skip (int): Number of records to skip.
        limit (int): Maximum number of records to return.

    Returns:
        List[College]: List of College instances.
    """
    result = await db.execute(select(College).offset(skip).limit(limit))
    return result.scalars().all()


async def create_college(db: AsyncSession, college_in):
    """
    Create a new college record.

    Args:
        db (AsyncSession): Asynchronous database session.
        college_in: Pydantic schema or dict with college data.

    Returns:
        College: The newly created College instance.
    """
    db_college = College(**college_in.dict())
    db.add(db_college)
    await db.commit()
    await db.refresh(db_college)
    return db_college


async def update_college(db: AsyncSession, college_id: UUID, college_in):
    """
    Update an existing college record.

    Args:
        db (AsyncSession): Asynchronous database session.
        college_id (UUID): The college's UUID.
        college_in: Pydantic schema or dict with updated data.

    Returns:
        College or None: The updated College instance, or None if not found.
    """
    db_college = await get_college(db, college_id)
    if not db_college:
        return None
    for field, value in college_in.dict(exclude_unset=True).items():
        setattr(db_college, field, value)
    await db.commit()
    await db.refresh(db_college)
    return db_college


async def delete_college(db: AsyncSession, college_id: UUID):
    """
    Delete a college record by its UUID.

    Args:
        db (AsyncSession): Asynchronous database session.
        college_id (UUID): The college's UUID.

    Returns:
        College or None: The deleted College instance, or None if not found.
    """
    db_college = await get_college(db, college_id)
    if not db_college:
        return None
    await db.delete(db_college)
    await db.commit()
    return db_college
