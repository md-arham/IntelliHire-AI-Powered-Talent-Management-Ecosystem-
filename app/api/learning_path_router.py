from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.db import get_db
from app.services.learning_path_service import generate_learning_path, get_learning_path
from app.utils.logger_config import logger
from app.schemas.learning_path_schemas import LearningPathRequest, LearningPathQuery, LearningPathResponse

router = APIRouter(
    prefix="/api/learning_path",
    tags=["Learning Path"],
    responses={
        404: {"description": "Not found"},
        500: {"description": "Failed to connect to Ollama. Please try again later."},
        503: {"description": "LLM service unavailable"},
    }
)

@router.post(
    "/generate",
    response_model=LearningPathResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate a personalized learning path",
    description="Generates a learning path based on interview feedback for a specific job and student.",
)
async def generate_learning_path_endpoint(
    request: LearningPathRequest = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate and store a learning path for a student based on interview feedback.

    - **request**: Contains job_id and student_id.
    """
    try:
        logger.info(f"Generating learning path for job_id: {request.job_id}, student_id: {request.student_id}")
        result = await generate_learning_path(request=request, db=db)
        logger.info(f"Generated learning path for feedback_id: {result.feedback_id}")
        return result
    except HTTPException as http_exc:
        logger.warning(f"HTTP error: {http_exc.detail} (Status: {http_exc.status_code})")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in generate_learning_path_endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate learning path",
        )

@router.get(
    "/get",
    response_model=LearningPathResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a stored learning path",
    description="Fetches a previously generated learning path for a specific job and student using query parameters.",
)
async def get_learning_path_endpoint(
    query: LearningPathQuery = Depends(LearningPathQuery),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve a stored learning path for a student based on interview feedback.

    - **job_id**: UUID of the job posting (query parameter).
    - **student_id**: UUID of the student (query parameter).
    """
    try:
        logger.info(f"Retrieving learning path for job_id: {query.job_id}, student_id: {query.student_id}")
        result = await get_learning_path(job_id=query.job_id, student_id=query.student_id, db=db)
        logger.info(f"Retrieved learning path for feedback_id: {result.feedback_id}")
        return result
    except HTTPException as http_exc:
        logger.warning(f"HTTP error: {http_exc.detail} (Status: {http_exc.status_code})")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_learning_path_endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve learning path",
        )