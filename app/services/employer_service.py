from typing import Any, Dict
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload, selectinload

from app.database.models.employer_profiles_models import EmployerProfile
from app.database.models.users_models import User
from app.schemas.employer_schemas import EmployerUpdateSchema


async def get_employer(db: AsyncSession, user_id: UUID):
    """
    Fetch an employer profile by user_id, including related user and company.

    Args:
        db (AsyncSession): Asynchronous database session.
        user_id (UUID): UUID of the user.

    Returns:
        EmployerProfile: Employer profile ORM instance.

    Raises:
        HTTPException: If the employer is not found.
    """
    result = await db.execute(
        select(EmployerProfile)
        .options(selectinload(EmployerProfile.user), selectinload(EmployerProfile.company))
        .where(EmployerProfile.user_id == user_id)
    )
    employer = result.scalars().first()
    if not employer:
        raise HTTPException(status_code=404, detail="Employer not found")
    return employer


async def get_all_employers(db: AsyncSession):
    """
    Fetch all employer profiles, including related user and company.

    Args:
        db (AsyncSession): Asynchronous database session.

    Returns:
        List[EmployerProfile]: List of employer profile ORM instances.
    """
    result = await db.execute(
        select(EmployerProfile)
        .options(selectinload(EmployerProfile.user), selectinload(EmployerProfile.company))
    )
    employers = result.scalars().all()
    return employers


class EmployerService:
    @staticmethod
    async def update_employer(
        db: AsyncSession, employer_id: UUID, employer_data: EmployerUpdateSchema
    ) -> Dict[str, Any]:
        """
        Update an employer profile and related company/user details.

        Args:
            db (AsyncSession): Asynchronous database session.
            employer_id (UUID): UUID of the employer to update.
            employer_data (EmployerUpdateSchema): Data for updating employer.

        Returns:
            dict: Status message and employer ID.

        Raises:
            HTTPException: If the employer or associated user is not found.
        """
        result = await db.execute(
            select(EmployerProfile)
            .options(selectinload(EmployerProfile.company))
            .where(EmployerProfile.employer_id == employer_id)
        )
        employer = result.scalars().first()
        if not employer:
            raise HTTPException(status_code=404, detail="Employer not found")

        # Update company fields from employer_data.company
        if employer_data.company and employer.company:
            company = employer.company
            if employer_data.company.name is not None:
                company.name = employer_data.company.name
            if employer_data.company.type is not None:
                company.type = employer_data.company.type
            if employer_data.company.description is not None:
                company.description = employer_data.company.description
            if employer_data.company.location is not None:
                company.location = employer_data.company.location
            if employer_data.company.logo_url is not None:
                company.logo_url = employer_data.company.logo_url
            if employer_data.company.website_url is not None:
                company.website_url = employer_data.company.website_url

            await db.flush()

        # Update user data if provided
        if employer_data.user:
            user_result = await db.execute(
                select(User).where(User.user_id == employer.user_id)
            )
            user = user_result.scalars().first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found for this employer")
            if employer_data.user.email is not None:
                user.email = employer_data.user.email
            if employer_data.user.full_name is not None:
                user.full_name = employer_data.user.full_name

        return {
            "status": "success",
            "message": "Employer details updated successfully",
            "employer_id": str(employer_id)
        }

