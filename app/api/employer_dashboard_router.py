from app.services.employer_candidate_match_service import get_top_candidate_matches_service
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from uuid import UUID
from app.services.employer_resume_extractor_service import (
    get_jobs_and_resumes_by_employer,
    process_resume_zip,
)
from app.database.db import get_db


router = APIRouter(prefix="/api/employer-dashboard",tags=["Employer Dashboard"])


@router.get("/top-matches/{user_id}")
async def get_top_candidate_matches(user_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Retrieve the top-matched candidate for each job posting by an employer.

    Args:
        user_id (UUID): The employer's user UUID.
        db (AsyncSession): Asynchronous database session.

    Returns:
        list: List of dictionaries, each containing the top-matched candidate's structured resume data,
              match score, job title, and job ID.

    Raises:
        HTTPException: If the employer is not found or there is a server/database error.
    """
    return await get_top_candidate_matches_service(user_id, db)


@router.post("/employer/{user_id}/job/{job_id}/upload-resume-zip")
async def upload_resume_zip(
    user_id: UUID, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)
):
    """
    Upload a ZIP file of resumes for a specific employer and job.

    Args:
        user_id (UUID): The employer's user UUID.
        file (UploadFile): The uploaded ZIP file containing resumes.
        db (AsyncSession): Asynchronous database session.

    Returns:
        dict: Result of the resume processing.

    Raises:
        HTTPException: If processing the ZIP file fails.
    """
    # Pass everything to the processor
    result = await process_resume_zip(db, user_id, file)
    return result


@router.get("/employer/{user_id}/referaljob-resumes")
async def get_employer_job_resumes(user_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Retrieve all job IDs and their matched resumes for a given employer.

    Args:
        user_id (UUID): The employer's user UUID.
        db (AsyncSession): Asynchronous database session.

    Returns:
        dict: Dictionary mapping job IDs to lists of resumes sorted by matching score.

    Raises:
        HTTPException: If there is a server/database error.
    """
    try:
        data = await get_jobs_and_resumes_by_employer(db, user_id)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
