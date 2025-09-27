from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.db import get_db
from app.services.employer_candidate_match_service import (
    get_matchedresumes_for_job,
    job_vectorStore,
    recommend_candidates,
)
from app.services.employer_candidate_match_service import (
    get_filtered_matchedresumes_for_job,
)

router = APIRouter(prefix="/api/jobs_candidateMatching", tags=["CandidateMatching"])


@router.post("/vectorStore/{job_id}")
async def summarize_job(job_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Summarize a job posting and store its vector in Qdrant.

    Args:
        job_id (UUID): UUID of the job to summarize and vectorize.
        db (AsyncSession): Asynchronous database session.

    Returns:
        dict: Result of vector storage (summary and status).

    Raises:
        HTTPException: If the job is not found or processing fails.
    """
    result = await job_vectorStore(job_id, db)
    if not result:
        raise HTTPException(
            status_code=404, detail="Job not found or failed to process"
        )
    return result



@router.get("/recommend/{job_id}")
async def recommend_candidates_for_job(job_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Recommend candidate resumes for a given job posting.

    Args:
        job_id (UUID): UUID of the job posting.
        db (AsyncSession): Asynchronous database session.

    Returns:
        dict: Dictionary containing recommended candidate IDs and details.

    Raises:
        HTTPException: If recommendation fails or no candidates are found.
    """
    result = await recommend_candidates(job_id, db)
    if not result or "error" in result:
        raise HTTPException(
            status_code=404, detail=result.get("error", "Recommendation failed")
        )
    return result


# ROUTE FOR MATCHED RESUMES
@router.get("/matched_resumes/{job_id}")
async def matched_resumes_for_job(job_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Get all matched candidate resumes for a given job posting.

    Args:
        job_id (UUID): UUID of the job posting.
        db (AsyncSession): Asynchronous database session.

    Returns:
        list: List of matched candidate resumes.

    Raises:
        HTTPException: If no matched resumes are found.
    """
    return await get_matchedresumes_for_job(job_id, db)


# ROUTE FOR filtered MATCHED RESUMES

@router.get("/filter_matched_resumes/{job_id}")
async def filtered_matched_resumes_for_job(
    job_id: UUID,
    degree_qualification: Optional[str] = Query(None),
    branch: Optional[str] = Query(None),
    passed_out_year: Optional[int] = Query(None),
    grade: Optional[float] = Query(None),
    college_type: Optional[str] = Query(None),
    matching_score: Optional[float] = Query(None),
    country: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),

    ):

    """
    Get all matched candidate resumes for a given job posting, with optional filters.

    Args:
        job_id (UUID): UUID of the job posting.
        degree_qualification (Optional[str]): Filter by degree qualification.
        branch (Optional[str]): Filter by branch/field of study.
        passed_out_year (Optional[int]): Filter by graduation year.
        grade (Optional[float]): Filter by minimum grade.
        college_type (Optional[str]): Filter by college type.
        matching_score (Optional[float]): Filter by minimum matching score.
        country (Optional[str]): Filter by country.
        region (Optional[str]): Filter by region.
        db (AsyncSession): Asynchronous database session.

    Returns:
        list: List of matched candidate resumes matching the filters.

    Raises:
        HTTPException: If no matched resumes are found.
    """
    return await get_filtered_matchedresumes_for_job(
        job_id=job_id,
        degree_qualification=degree_qualification,
        branch=branch,
        passed_out_year=passed_out_year,
        grade=grade,
        college_type=college_type,
        matching_score=matching_score,
        country=country,
        region=region,
        db=db,
    )