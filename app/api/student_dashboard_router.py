from sqlalchemy import select
from app.services.sentiment_services import get_grouped_trends_by_sentiment, get_latest_sentiment_data
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from app.database.db import get_db
from app.database.models.students_models import Student
from app.schemas.employer_schemas import EmployerFilterParams
from app.services.student_dashboard_service import get_employer_profiles_for_user,get_dashboard_stats_for_user

router = APIRouter(prefix="/api/student-dashboard",tags=["Student Dashboard"])


@router.get("/student/{user_id}")
async def get_dashboard_stats(user_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Retrieve job search dashboard statistics for a student.

    This endpoint provides a summary of the student's engagement with the job platform, including:
    - The total number of active job postings available.
    - The number of internships recommended to the student via resume screening.
    - A count of the student's job applications grouped by application status (e.g., Applied, Shortlisted, Rejected).

    Args:
        user_id (UUID): The unique identifier of the user (student).
        db (AsyncSession): Dependency-injected database session.

    Returns:
        dict: A JSON object with the following keys:
            - total_postings (int): Total count of currently active job postings.
            - recommended_internships (int): Number of resume-screened internship recommendations.
            - job_application_status_counts (dict): Dictionary with status names as keys and application counts as values.

    Raises:
        HTTPException:
            - 404: If no student is found for the given user_id.
            - 500: For any database or internal errors encountered during processing.
    """
    return await get_dashboard_stats_for_user(user_id, db)


@router.get("/employers/{user_id}")
async def get_employer_profiles(
    user_id: UUID,
    filters: EmployerFilterParams = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    (Employers looking at you feature) Get all unique employer profiles that have considered or matched with the student's resume.
    Optional filters for company type and location available.
    """
    return await get_employer_profiles_for_user(
        user_id, 
        db, 
        company_type=filters.company_type
    )


@router.get("/sentiment-dashboard/{user_id}")
async def get_student_sentiment_dashboard(user_id: UUID, db: AsyncSession = Depends(get_db)):

    """
    Retrieve the sentiment analysis dashboard for a student.

    This endpoint provides a detailed overview of the student's interview sentiment feedback:
    
    1. **Latest Sentiment**: 
       - Retrieves the most recent Level-1 interview feedback.
       - Includes sentiment classification (positive/neutral/negative), a confidence score, and associated job metadata.
    
    2. **Historical Trends**: 
       - Groups past Level-1 interview feedback by sentiment type.
       - Each group shows a time series of sentiment scores over time, useful for visualizing progress or trends.

    Args:
        user_id (UUID): The unique identifier for the student (linked via the user model).
        db (AsyncSession): SQLAlchemy async session dependency for database access.

    Returns:
        dict: A dictionary containing:
            - "latest_sentiment": Details of the most recent sentiment feedback including score and related job metadata.
            - "trends": Grouped sentiment score trends for past interviews categorized by sentiment type.

    Raises:
        HTTPException: 
            - 404 if the student with the given user_id is not found.
            - 500 if database access for latest sentiment or trend data fails.
    """


    # Step 1: Find student_id from user_id
    student_result = await db.execute(
        select(Student).where(Student.user_id == user_id)
    )
    student = student_result.scalars().first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    student_id = student.student_id

    # Step 2: Fetch latest sentiment data
    latest_sentiment_data = await get_latest_sentiment_data(db, student_id)

    # Step 3: Fetch and group trends
    grouped_trends = await get_grouped_trends_by_sentiment(db, student_id)

    return {
        "latest_sentiment": latest_sentiment_data,
        "trends": grouped_trends
    }
