import json
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import joinedload
from app.database.models.job_postings_models import JobPosting
from app.database.models.interview_feedback_models import InterviewFeedback
from app.database.models.interview_sessions_models import InterviewSession
from app.utils.logger_config import logger
from app.services.job_postings_llm_service import call_llama
from app.schemas.learning_path_schemas import LearningPathRequest, LearningPathResponse
from pydantic import UUID4

async def generate_learning_path(
    request: LearningPathRequest,
    db: AsyncSession,
) -> LearningPathResponse:
    """
    Generates a learning path for a student based on interview feedback for a specific job.

    Args:
        request (LearningPathRequest): Contains job_id and student_id.
        db (AsyncSession): The asynchronous database session.

    Returns:
        LearningPathResponse: Contains the feedback_id and generated learning_path.

    Raises:
        HTTPException: If validation, database, or LLM operations fail.
    """
    job_id = request.job_id
    student_id = request.student_id

    # Validate job existence
    job = (await db.execute(select(JobPosting).filter(JobPosting.job_id == job_id))).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job posting with ID {job_id} not found")

    # Fetch feedback with related session and student in one query
    stmt = (
        select(InterviewFeedback)
        .options(
            joinedload(InterviewFeedback.session)
            .joinedload(InterviewSession.student)
        )
        .join(InterviewSession, InterviewFeedback.session_id == InterviewSession.session_id)
        .filter(
            and_(
                InterviewFeedback.job_id == job_id,
                InterviewSession.student_id == student_id,
            )
        )
        .order_by(InterviewFeedback.submitted_at.desc())
    )
    feedback = (await db.execute(stmt)).scalar_one_or_none()

    if not feedback or not feedback.session or not feedback.session.student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No feedback found for the given job and student",
        )

    feedback_id = feedback.feedback_id
    areas_of_improvement = feedback.areas_of_improvement or []
    skill_recommendations = feedback.skill_recommendations or []

    # Construct LLM prompt
    prompt = f"""You are an expert career coach specializing in personalized learning paths.
Based on the following areas of improvement and skill recommendations from an interview,
generate a learning path to help the candidate improve their skills and performance.
The learning path should include:
- A list of relevant courses (2-3) to address the areas of improvement and build recommended skills.
- A list of resources (e.g., books, websites, videos, tools) to support learning.

**Areas of Improvement:**
{', '.join(areas_of_improvement) if areas_of_improvement else 'None provided'}

**Skill Recommendations:**
{', '.join(skill_recommendations) if skill_recommendations else 'None provided'}

**Instructions:**
- Provide a structured JSON object with two keys: `courses` and `resources`.
- `courses`: List of 2-3 specific course names (e.g., "Introduction to Python Programming").
- `resources`: List of 2-3 specific resources (e.g., "Python Crash Course book").
- Ensure relevance to the areas of improvement and skill recommendations.
- Return ONLY the JSON object as a string, without additional text.

Example Output:
{{
  "courses": ["Introduction to Python Programming", "Data Structures and Algorithms"],
  "resources": ["Python Crash Course book", "LeetCode practice problems"]
}}
"""

    # Call LLM and parse response
    learning_path = {"courses": [], "resources": []}
    try:
        llm_response = await call_llama(prompt=prompt, temp=0.2)
        logger.info(f"Raw LLM response: {llm_response}")
        cleaned_response = llm_response.strip()
        if cleaned_response.startswith("```json"):
            cleaned_response = cleaned_response[7:].rstrip("```").strip()
        learning_path = json.loads(cleaned_response)
        if not isinstance(learning_path, dict) or "courses" not in learning_path or "resources" not in learning_path:
            logger.error(f"Invalid learning path format: {cleaned_response}")
            raise ValueError("Invalid learning path format")
    except (json.JSONDecodeError, ValueError) as llm_error:
        logger.error(f"LLM error: {str(llm_error)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to generate learning path due to LLM service error. Please try again later.",
        )

    # Update feedback with learning path
    try:
        logger.info(f"Assigning learning_path: {learning_path}")
        feedback.learning_path = learning_path
        db.add(feedback)
        await db.commit()
        await db.refresh(feedback)
        logger.info(f"Stored learning_path for feedback_id: {feedback_id}, Value: {feedback.learning_path}")
    except Exception as db_error:
        await db.rollback()
        logger.error(f"Database error updating learning_path: {str(db_error)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save learning path",
        )

    return LearningPathResponse(
        feedback_id=feedback_id,
        learning_path=learning_path,
    )

async def get_learning_path(
    job_id: UUID4,
    student_id: UUID4,
    db: AsyncSession,
) -> LearningPathResponse:
    """
    Retrieves a stored learning path for a student based on interview feedback.

    Args:
        job_id (UUID4): The UUID of the job posting.
        student_id (UUID4): The UUID of the student.
        db (AsyncSession): The asynchronous database session.

    Returns:
        LearningPathResponse: Contains the feedback_id and stored learning_path.

    Raises:
        HTTPException: If validation or database operations fail.
    """
    # Validate job existence
    job = (await db.execute(select(JobPosting).filter(JobPosting.job_id == job_id))).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job posting with ID {job_id} not found")

    # Fetch feedback with related session and student
    stmt = (
        select(InterviewFeedback)
        .options(
            joinedload(InterviewFeedback.session)
            .joinedload(InterviewSession.student)
        )
        .join(InterviewSession, InterviewFeedback.session_id == InterviewSession.session_id)
        .filter(
            and_(
                InterviewFeedback.job_id == job_id,
                InterviewSession.student_id == student_id,
                InterviewFeedback.learning_path is not None,
            )
        )
        .order_by(InterviewFeedback.submitted_at.desc())
    )
    feedback = (await db.execute(stmt)).scalar_one_or_none()

    if not feedback or not feedback.learning_path or not feedback.session or not feedback.session.student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No learning path found for the given job and student",
        )

    return LearningPathResponse(
        feedback_id=feedback.feedback_id,
        learning_path=feedback.learning_path,
    )