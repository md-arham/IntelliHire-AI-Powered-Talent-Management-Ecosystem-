import uuid
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database.db import get_db
from app.database.models.interview_expirence_feedback_models import (
    InterviewExperienceFeedback,
)
from app.database.models.interview_question_responses_models import (
    InterviewQuestionResponse,
)
from app.schemas.interview_expirence_feedback_schemas import (
    InterviewExperienceFeedbackCreate,
)
from app.schemas.interview_schema import (
    ShortlistedCandidatesResponse,
    BulkUpdateAnswerRequest,
    StoreCompleteInterviewRequest,
)
from app.services.interview_service import (
    create_session_with_questions,
    fetch_all_l1_candidates,
    generate_questions,
    store_complete_interview_analysis,
    fetch_all_feedback_for_user
)

from app.services.sentiment_services import store_feedback_sentiment
from app.utils.logger_config import logger

router = APIRouter(prefix="/api/v1/interviews",tags=["Interviews"])



@router.post("/bulk-update-answers")
async def bulk_update_answers(
    payload: BulkUpdateAnswerRequest, db: AsyncSession = Depends(get_db)
):
    """
    Efficiently update multiple interview question responses in a single DB transaction.

    Steps:
      1. Extract all `question_id`s from the input payload.
      2. Fetch matching `InterviewQuestionResponse` rows in a single DB query using `.in_()`.
      3. Update each matched response's `user_answer` in memory.
      4. Commit the changes once after all updates.

    Parameters:
        payload (BulkUpdateAnswerRequest): Contains `session_id` and a list of `question_id` + `user_answer` pairs.
        db (AsyncSession): SQLAlchemy session.

    Returns:
        dict: {
            "status": "success",
            "updated_count": int
        }

    Raises:
        HTTPException(404): If none of the `question_id`s were found for the given session.
        HTTPException(500): On any database commit failure.
    """


    question_ids = [item.question_id for item in payload.answers]
    response_query = await db.execute(
        select(InterviewQuestionResponse).where(
            InterviewQuestionResponse.session_id == payload.session_id,
            InterviewQuestionResponse.question_id.in_(question_ids)
        )
    )
    responses = {r.question_id: r for r in response_query.scalars().all()}

    # Step 2: Update in memory
    updated_count = 0
    for item in payload.answers:
        if item.question_id in responses:
            responses[item.question_id].user_answer = item.user_answer
            updated_count += 1
        else:
            logger.warning(f"No question found: {item.question_id} for session: {payload.session_id}")

    # Step 3: Finalize
    if updated_count == 0:
        raise HTTPException(status_code=404, detail="No valid question responses found to update.")

    await db.commit()
    return {"status": "success", "updated_count": updated_count}




@router.post("/store-interview")
async def store_complete_interview_analysis_endpoint(
    payload: StoreCompleteInterviewRequest, db: AsyncSession = Depends(get_db)
):
    """
    Evaluate all answers in an interview session and store L1 feedback.

    Steps:
      1. Fetch all `InterviewQuestionResponse` rows for the session.
      2. Evaluate each answer using LLM (with resume context for Q1, Q2).
      3. Compute overall score and generate detailed feedback.
      4. Insert new `InterviewFeedback` record.
      5. Update `JobApplication.status` to 'Shortlisted' or 'Rejected'.

    Parameters:
        payload (StoreCompleteInterviewRequest): Contains `session_id`.
        db (AsyncSession): SQLAlchemy session.

    Returns:
        dict: {
            "status": "success",
            "feedback_id": UUID,
            ...other analysis fields
        }

    Raises:
        HTTPException(404): If session or responses are not found.
        HTTPException(500): On DB or LLM failure.
    """


    result = await store_complete_interview_analysis(db, payload)
    return JSONResponse(content=jsonable_encoder({"status": "success", **result}))


@router.get(
    "/short-listed-candidates/{job_id}",
    response_model=ShortlistedCandidatesResponse,
)
async def get_shortlisted_candidates_endpoint(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch all L1-evaluated candidates for a specific job posting.

    Steps:
      1. Join `InterviewFeedback` → `InterviewSession` → `JobApplication` → `Student` → `User`.
      2. Filter by `feedback_type == L1` and known job ID.
      3. Compute and return 0–100 scaled scores.

    Parameters:
        job_id (UUID): Unique ID of the job posting.
        db (AsyncSession): SQLAlchemy database session.

    Returns:
        ShortlistedCandidatesResponse: List of shortlisted or rejected candidates with scores.

    Raises:
        HTTPException(500): On unexpected database errors.
    """


    try:
        candidates = await fetch_all_l1_candidates(db, job_id)
        return ShortlistedCandidatesResponse(status="success", candidates=candidates)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


@router.post("/generate-interview-questions")
async def generate_interview_questions_endpoint(
    job_application_id: Optional[UUID] = Form(None),
    student_id: UUID = Form(...),
    role: str = Form(...),
    audio_link: Optional[str] = Form(None),
    is_video_enabled: bool = Form(False),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate interview questions and initialize a new InterviewSession.

    Steps:
      1. Use `job_application_id` to fetch resume and JD.
      2. Generate questions using LLM from both resume and JD.
      3. Create a new `InterviewSession` and insert blank responses.

    Parameters:
        job_application_id (UUID): Application reference for the candidate.
        student_id (UUID): Student's ID.
        role (str): Interview role title.
        audio_link (str, optional): URL to recorded audio.
        is_video_enabled (bool): Flag indicating if video is enabled.
        db (AsyncSession): SQLAlchemy session.

    Returns:
        dict: {
            "status": "success",
            "session_id": UUID,
            "questions": [ { "question_id": str, "question": str }, ... ]
        }

    Raises:
        HTTPException(400): If job_application_id is missing.
        HTTPException(500): On LLM or DB failure.
    """

    if not job_application_id:
        raise HTTPException(status_code=400, detail=" job_application_id required.")

    try:
        questions = await generate_questions(db, job_application_id)
        result = await create_session_with_questions(
            db=db,
            student_id=student_id,
            questions=questions,
            job_application_id=job_application_id,
            role=role,
            audio_link=audio_link,
            is_video_enabled=is_video_enabled,
        )
        return JSONResponse(content={"status": "success", **result})
    except Exception as e:
        logger.error(f"Error generating interview questions: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate questions.")



@router.post("/feedback/experience", status_code=201)
async def submit_interview_experience_feedback(
    feedback: InterviewExperienceFeedbackCreate, db: AsyncSession = Depends(get_db)
):
    """
    Submit candidate experience feedback post-interview.

    Steps:
      1. Insert a new `InterviewExperienceFeedback` record.
      2. Trigger sentiment analysis using the submitted feedback.

    Parameters:
        feedback (InterviewExperienceFeedbackCreate): User feedback fields.
        db (AsyncSession): SQLAlchemy database session.

    Returns:
        dict: {
            "feedback_id": UUID,
            "message": "Feedback submitted successfully"
        }

    Raises:
        HTTPException(500): On database commit failure.
    """


    feedback_id = uuid.uuid4()
    db_feedback = InterviewExperienceFeedback(
        feedback_id=feedback_id,
        session_id=feedback.session_id,
        overall_experience=feedback.overall_experience,
        question_relevance=feedback.question_relevance,
        question_clarity=feedback.question_clarity,
        ease_of_use=feedback.ease_of_use,
        suggestions=feedback.suggestions,
    )
    db.add(db_feedback)
    await db.commit()
    await db.refresh(db_feedback)
    await store_feedback_sentiment(
        db, feedback_id, feedback.session_id, feedback.job_id
    )
    return {
        "feedback_id": str(db_feedback.feedback_id),
        "message": "Feedback submitted successfully",
    }

@router.get("/feedback/{user_id}")
async def get_all_feedback(user_id: UUID, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """
    Fetch both L1 and Mock feedback for a student.

    Steps:
      1. Resolve student via `user_id`.
      2. Fetch all `InterviewSessions` and attached L1 feedback.
      3. Fetch all `MockInterviewSessions`.
      4. Attach job metadata (company_name, title) to L1 entries.

    Parameters:
        user_id (UUID): UUID of the student (from `users` table).
        db (AsyncSession): SQLAlchemy session.

    Returns:
        dict: {
            "MOCK": [{ "session_id": ..., "score": ..., "created_at": ... }],
            "L1": [{ "session_id": ..., "feedback_id": ..., ... }]
        }

    Raises:
        HTTPException(404): If student not found.
        HTTPException(500): On DB error.
    """


    try:
        result = await fetch_all_feedback_for_user(user_id, db)
        return JSONResponse(content=result)
    except HTTPException as e:
        logger.error(f"Feedback fetch error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected feedback fetch error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
