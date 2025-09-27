from app.schemas.job_postings_schema import PaginatedInternshipResponse
from app.services.internships_service import InternshipRepository, get_paginated_external_internships
from app.services.job_postings_services import get_paginated_internal_internships
from app.utils.logger_config import logger
from app.schemas.internships_schema import InternshipFilterRequest
from fastapi import HTTPException, status, APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.db import get_db
from app.database.models.job_postings_models import JobOriginType
from app.utils.internships_run_scraper import run_scraper
from app.services.internships_recommendation_service import (
    get_filtered_paginated_recommended_internships,
    upload_internships_to_qdrant_v2,
    get_recommendations_by_resume_version,
)
from app.services.resume_screener_service import (
    recommend_jobs_combined,
)
from uuid import UUID

router = APIRouter(prefix="/api/internships", tags=["Internships"])

# TODO: Combine the get Internships router with the Job Postings Router
    
@router.post("/fetch", response_model=PaginatedInternshipResponse)
async def get_internships_paginated(request: InternshipFilterRequest,db: AsyncSession = Depends(get_db)):
    """
    Fetch paginated internships or job postings based on filters and job origin.

    This endpoint retrieves a paginated list of internships or internal job postings
    based on the specified filters such as job type, location, category, title, etc.
    It determines the source (internal or external) using the `job_origin` field
    and routes the request to the appropriate service logic.

    Filtering options include:
    - Internship type: Remote, Onsite, Hybrid
    - Job type: Full-Time, Part-Time, etc.
    - Location (including remote filtering)
    - Category and Title
    - Pagination (page number and page size)

    Args:
        request (InternshipFilterRequest): Filters and pagination parameters.
        db (AsyncSession): Asynchronous database session dependency.

    Returns:
        PaginatedInternshipResponse: Paginated list of job postings along with metadata like
        total records, total pages, and page number.

    Raises:
        HTTPException: 400 if an unsupported job origin is provided,
                       500 for internal server/database errors.
    """
    try:
        if request.job_origin == JobOriginType.EXTERNAL:
            return await get_paginated_external_internships(request, db)

        elif request.job_origin == JobOriginType.INTERNAL:
            return await get_paginated_internal_internships(request, db)

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported job origin: {request.job_origin}",
            )

    except Exception as e:
        logger.exception(f"Error fetching paginated internships: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching internships.",
        )


@router.get("/populate")
async def populate_internships(db: AsyncSession = Depends(get_db)) -> dict:
    """
    Trigger scraping of internships and upload them to Qdrant.

    Returns:
        dict: Status and number of internships vectorized.
    """
    await run_scraper()
    return await upload_internships_to_qdrant_v2(db=db)


@router.delete("/deactivate-expired")
async def deactivate_expired_internships(db: AsyncSession = Depends(get_db)) -> dict:
    """
    This is a utility endpoint to check the working of deactivate_expired_internships

    Deactivate internships whose application deadlines have passed.

    This endpoint finds internships where the `application_deadline` is earlier than today
    and marks them as inactive in the database.

    Args:
        db (AsyncSession): Asynchronous DB session injected by FastAPI.

    Returns:
        dict: A response message indicating the number of internships deactivated.
    """
    try:
        repository = InternshipRepository(db)
        result_message = await repository.deactivate_expired_internships_service()
        return {"message": result_message}
    except RuntimeError as e:
        logger.error(f"Failed to deactivate expired internships: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/internship-vector-store")
async def internshipVectorStore_v2(db: AsyncSession = Depends(get_db)) -> dict:
    """
    This is a utility endpoint to check the working of the upload_internships_to_qdrant function

    API endpoint to upload recent internships into Qdrant.

    Args:
        db (AsyncSession): Dependency-injected async DB session.

    Returns:
        dict: Upload status and count of internships processed.
    """
    return await upload_internships_to_qdrant_v2(db=db)


# Recommend internships APIs
@router.post("/fetch-recommended", response_model=PaginatedInternshipResponse)
async def get_matched_jobs_to_student(
    request: InternshipFilterRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve paginated and filtered recommended internships (internal or external) for a student.

    This endpoint returns a personalized list of internship recommendations for the student,
    combining resume screening results with internship metadata. It supports filtering and pagination
    similar to the general internship listings, and ensures consistency across internal and external jobs.

    Key features:
    - Filters based on job origin (internal/external), job type, work type, title, location, etc.
    - Applies pagination with page number and page size.
    - Sorts the recommended internships based on ATS matching score.
    - Adds `matching_score` and `matching_reason` to `additional_info` of each job.
    - Marks jobs as bookmarked if already saved by the student.
    - Applies `is_active` check to exclude inactive jobs.
    - Automatically applies `refactor_response()` transformation to external job data.

    Args:
        request (InternshipFilterRequest): Contains user_id, job origin, filters, and pagination inputs.
        db (AsyncSession): Async SQLAlchemy session for DB operations.

    Returns:
        PaginatedInternshipResponse: A paginated response containing a filtered list of recommended internships,
                                     each with metadata, ATS score, bookmark status, and filtering applied.

    Raises:
        HTTPException: 404 if student is not found.
        HTTPException: 500 for any internal server or database errors.
    """
    return await get_filtered_paginated_recommended_internships(request, db)



@router.post("/match")
async def match_jobs_to_student(user_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Match a student's resume with both internal and external job opportunities.

    This endpoint:
    - Retrieves the student's latest resume vector from Qdrant.
    - Performs a similarity search against external internships.
    - Scrolls through internal job postings and matches using both vector similarity and metadata payload rules.
    - Deduplicates results to avoid inserting the same job matches repeatedly.
    - Inserts matched jobs into ResumeScreeningInternship.
    - If internal jobs are matched, also updates employer-side records in JobCandidateScreening and JobCandidateMatching.

    Args:
        user_id (UUID): The unique ID of the user (student).
        db (Session): The SQLAlchemy session, injected via FastAPI's dependency system.

    Returns:
        dict: {
            "user_id": str,
            "student_id": str,
            "screening_id": str,
            "matched_internal_jobs": List[str],   # List of internal job UUIDs matched in this call
            "matched_external_jobs": List[str]    # List of external internship UUIDs matched in this call
        }

    Raises:
        HTTPException:
            - 404 if the student is not found.
            - 500 for Qdrant errors, DB failures, or unexpected exceptions.
    """
    return await recommend_jobs_combined(user_id, db)


@router.post("internship-recommendations/by-resume-version", response_model=dict)
async def internship_recommendations_grouped_by_resume(
    data: UUID, db: AsyncSession = Depends(get_db)
):
    """
    Generate combined internal and external internship recommendations
    grouped by each resume version for the student.

    Args:
        data (UserIDRequest): Request body with user_id.
        db (AsyncSession): Asynchronous DB session.

    Returns:
        dict: Resume name mapped to a list of recommended internships (with scores and sources).
    """
    return await get_recommendations_by_resume_version(data.user_id, db)
