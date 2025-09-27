from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.db import get_db
from app.schemas.mock_interview_schema import (
    EvaluateQuestionsRequest,
    SkillsProficienciesRequest,
)
from app.services.mock_interview_services import (
    evaluate_answers,
    fetch_questions_by_skills,
    fetch_user_skills,
    get_score,
)
from app.utils.logger_config import logger

router = APIRouter(prefix="/api/mock-interview",tags=["Mock-Interview"])


@router.get("/get-skills")
async def get_user_skills_endpoint(
    user_id: UUID = Query(..., description="UUID of the user"), db: AsyncSession = Depends(get_db)
):
    """
    Fetch all technical skills for a user based on their resume.

    This endpoint retrieves skills linked to a user's resume if their category is 
    'Programming Language' or 'Tool/Technology'. The user ID is mapped to the student's resume 
    via the Student and PersonalInfo tables.

    Args:
        user_id (UUID): The unique identifier of the user.
        db (Session): SQLAlchemy database session dependency.

    Returns:
        JSONResponse: A success response containing a list of skill dictionaries with 
        fields: id, user_id, skill_name, and category.

    Raises:
        HTTPException 404: If no student, personal info, or skills are found.
        HTTPException 400: For any bad request or invalid input.
        HTTPException 500: For internal server errors.
    """
    try:
        skills = await fetch_user_skills(db, user_id)
        return JSONResponse(content={"status": "success", "skills": skills})
    except ValueError as e:
        logger.error(f"Error fetching skills for user_id {user_id}: {str(e)}")
        if str(e) == "No skills found for the provided user_id":
            raise HTTPException(
                status_code=404, detail=f"No skills found for user_id: {user_id}"
            )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching skills for user_id {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/get-questions-by-skills")
async def get_questions_by_skills_endpoint(
    payload: SkillsProficienciesRequest, db: AsyncSession = Depends(get_db)
):
    """
    Fetch up to 10 questions based on provided skills and proficiency levels.

    Args:
        payload (SkillsProficienciesRequest): Dict mapping skills to proficiency levels.
        db (Session): SQLAlchemy database session.

    Returns:
        JSONResponse: List of up to 10 questions with id, question_text, topic, and proficiency.

    Raises:
        HTTPException: 400 if payload is invalid, 404 if no questions found, 500 for server errors.
    """
    try:
        questions, session_id = await fetch_questions_by_skills(
            db, payload.user_id, payload.skills
        )
        return JSONResponse(
            content={
                "status": "success",
                "questions": questions,
                "session_id": session_id,
            }
        )
    except ValueError as e:
        logger.error(f"Error fetching questions for skills: {str(e)}")
        if str(e) == "No questions found for the provided skills and proficiencies":
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching questions for skills: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/evaluate-questions")
async def evaluate_questions_endpoint(
    payload: EvaluateQuestionsRequest, db: AsyncSession = Depends(get_db)
):
    """
    Evaluate user responses to mock interview questions and calculate the score.

    This endpoint compares user-selected answer IDs with the correct ones from the database,
    stores the results in the database, and calculates the total score.

    Args:
        payload (EvaluateQuestionsRequest): Contains user_id, session_id, and a dictionary 
        mapping question_id to answer_id.
        db (Session): SQLAlchemy database session dependency.

    Returns:
        JSONResponse: A success response with the total score obtained by the user.

    Raises:
        HTTPException 400: For any invalid payload or evaluation error.
        HTTPException 500: For internal server errors.
    """
    try:
        score = await evaluate_answers(
            db, payload.user_id, payload.session_id, payload.responses
        )
        return JSONResponse(content={"status": "success", "score": score})
    except ValueError as e:
        logger.error(f"Error evaluating questions: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error evaluating questions: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.get("/get-score")
async def get_score_endpoint(
    user_id: UUID = Query(..., description="UUID of the user"),
    session_id: UUID = Query(..., description="UUID of the session"),
    db: AsyncSession = Depends(get_db)):
    """
    Retrieve the final score for a given mock interview session.

    Fetches the stored score for a session linked to a given user and session ID.

    Args:
        payload (GetScoreRequest): Contains user_id and session_id.
        db (Session): SQLAlchemy database session dependency.

    Returns:
        JSONResponse: A success response with the score as part of the response object.

    Raises:
        HTTPException 400: If score retrieval fails due to a logical error.
        HTTPException 500: For internal server errors.
    """
    try:
        score = await get_score(db, user_id, session_id)
        return JSONResponse(content={"status": "success", "response": score})
    except ValueError as e:
        logger.error(f"Error getting score for questions: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting score for questions: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")