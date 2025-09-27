from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Any, Dict, List
from uuid import UUID

from app.database.db import get_db
from app.database.models.employer_profiles_models import EmployerProfile
from app.schemas.employer_schemas import EmployerResponse, EmployerUpdateSchema
from app.services.employer_service import (
    EmployerService,
    get_all_employers,
    get_employer,
)

from fastapi.responses import StreamingResponse

from app.services.employer_job_applications_service import export_applicants_to_excel
from app.schemas.employer_schemas import ExportApplicantsRequest


router = APIRouter(prefix="/api/employers", tags=["Employers"])


@router.get("/get_employers/", response_model=List[EmployerResponse])
async def list_employers(db: AsyncSession = Depends(get_db)):
    """
    Retrieve all employer profiles.

    Args:
        db (AsyncSession): Asynchronous database session.

    Returns:
        List[EmployerResponse]: List of employer profiles.

    Raises:
        HTTPException: If there's an error fetching employers.
    """
    return await get_all_employers(db)


@router.get("/get_employer/{user_id}", response_model=EmployerResponse)
async def retrieve_employer(user_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Retrieve a specific employer by user ID.

    Args:
        user_id (UUID): UUID of the user associated with the employer.
        db (AsyncSession): Asynchronous database session.

    Returns:
        EmployerResponse: Employer profile details.

    Raises:
        HTTPException: If the employer is not found.
    """
    return await get_employer(db, user_id)


@router.patch("/update_employer/{user_id}", response_model=Dict[str, Any])
async def update_employer_by_user(
    user_id: UUID,
    employer_data: EmployerUpdateSchema,
    db: AsyncSession = Depends(get_db),
):
    """
    Update employer details using user_id (partial update).

    Args:
        user_id (UUID): UUID of the user associated with the employer.
        employer_data (EmployerUpdateSchema): Data for updating employer profile.
        db (AsyncSession): Asynchronous database session.

    Returns:
        dict: Status message and employer ID.

    Raises:
        HTTPException: If employer not found or update fails.
    """
    try:
        # Find employer by user_id
        result = await db.execute(
            select(EmployerProfile).where(EmployerProfile.user_id == user_id)
        )
        employer = result.scalars().first()

        if not employer:
            raise HTTPException(
                status_code=404, detail="Employer not found for this user_id."
            )

        # Update employer using async service
        result = await EmployerService.update_employer(
            db, employer.employer_id, employer_data
        )

        await db.commit()
        return result

    except HTTPException as e:
        await db.rollback()
        raise e
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to update employer details: {str(e)}"
        )


@router.post("/applicants", summary="Export job applicants to Excel")
async def export_applicants(
    request: ExportApplicantsRequest, db: AsyncSession = Depends(get_db)
):
    """
    Export applicant data for a specific job to an Excel file with resume download links.

    The Excel file includes:
    - student_name (from users.full_name)
    - student_email (from users.email)
    - resume (clickable link to resume PDF)
    - job_title (from job_postings.title)

    Request:
    - job_id: UUID of the job posting to export data for

    Returns:
    - Excel file as a downloadable attachment
    """
    try:
        job_id = request.job_id
        excel_data = await export_applicants_to_excel(db, job_id)

        filename = f"applicants_job_{job_id}.xlsx"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

        return StreamingResponse(
            content=excel_data,
            headers=headers,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except HTTPException:
        raise
