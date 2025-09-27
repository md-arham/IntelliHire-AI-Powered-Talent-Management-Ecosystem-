from typing import List, Optional
from uuid import UUID, uuid4
import asyncio
import fitz
from fastapi.exceptions import HTTPException 
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.database.models.enums_models import JobApplicationStatus
from app.database.models.interview_feedback_models import (
    FeedbackType,
    InterviewFeedback,
)
from app.database.models.interview_question_responses_models import (
    InterviewQuestionResponse,
)
from app.database.models.resume_versions_models import ResumeVersion
from app.database.models.mock_interview_models import MockInterviewSession
from app.database.models.interview_sessions_models import InterviewSession
from app.database.models.job_applications_models import JobApplication
from app.database.models.job_postings_models import JobPosting
from app.database.models.students_models import Student
from app.prompt_templates.interview_prompt_templates import (
    answer_evaluation_prompt,
    full_interview_analysis_prompt,
    jd_based_question_prompt,
    resume_based_answer_evaluation_prompt,
    resume_based_question_prompt,
)
from app.schemas.interview_schema import (
    AnswerEval,
    FullInterviewAnalysis,
    GenrateQuestions,
    ShortlistedCandidate,
    StoreCompleteInterviewRequest,
)
from httpx import TimeoutException, RequestError
from app.utils.logger_config import logger
from app.utils.settings import ollama_async_client , settings


#centralized LLM Call for all the llm query functions
async def _call_llm(model: str , system_prompt: str, user_content: str, schema):
    """
    Invoke the configured LLM asynchronously and parse its JSON output into a Pydantic schema.

    Parameters:
        model (str): Identifier of the LLM model to use (e.g., settings.OLLAMA_MODEL).
        system_prompt (str): System-level instruction guiding the behavior of the LLM.
        user_content (str): The user-visible content or context to feed into the LLM.
        schema: Pydantic model class used to validate and parse the LLM's JSON response.

    Returns:
        An instance of the provided Pydantic schema, populated with data from the LLM response.

    Raises:
        HTTPException(503): If the LLM call fails or returns invalid data.
    """
    try:
        resp = await ollama_async_client.chat(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            options={"temperature": 0.4},
            format=schema.model_json_schema(),
        )
        data = resp["message"]["content"]
        return schema.model_validate_json(data)
    except TimeoutException as e:
        logger.error(f"LLM timeout: {e}")
        raise HTTPException(status_code=408, detail="LLM request timed out")

    except RequestError as e:
        logger.error(f"LLM connection error: {e}")
        raise HTTPException(status_code=503, detail="LLM service unreachable")

    except Exception as e:
        logger.exception(f"Internal LLM processing error: {str(e)}")
        raise HTTPException(status_code=500, detail="error during LLM processing")

#to read the bytes data from the bytea column
async def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """
    Extracts and concatenates text from each page of a PDF provided as raw bytes.

    Parameters:
        pdf_bytes (bytes): Binary content of a PDF file (BYTEA from the database).

    Returns:
        str: The full text extracted from the PDF, with page breaks preserved by newlines.

    Raises:
        HTTPException(400): If the input is not a valid PDF or contains no extractable text.
    """
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            text = "\n".join(page.get_text() for page in doc)
        if not text.strip():
            raise ValueError("Empty PDF content")
        return text
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid PDF data")


async def generate_questions(
    db: AsyncSession,
    job_application_id: UUID,
    resume_count: int = 2,
    jd_count: int = 3,
) -> List[str]:
    """
    Generate interview questions based on a candidate's resume and job description
    using parallel LLM calls.

    Parameters:
        db (AsyncSession): SQLAlchemy session.
        job_application_id (UUID): ID of the job application to pull resume/JD from.
        resume_count (int): Number of resume-based questions.
        jd_count (int): Number of JD-based questions.

    Returns:
        List[str]: Combined list of questions from resume and JD.
    """
    # Fetch JobApplication with nested relationships
    job_app_query = await db.execute(
        select(JobApplication)
        .options(
            selectinload(JobApplication.resume_version),
            selectinload(JobApplication.job)
        )
        .where(JobApplication.application_id == job_application_id)
    )
    job_app = job_app_query.scalar_one_or_none()
    if not job_app:
        raise HTTPException(status_code=404, detail="Job application not found")

    resume: ResumeVersion = job_app.resume_version
    job: JobPosting = job_app.job
    questions: List[str] = []

    resume_task = None
    jd_task = None

    # Prepare resume LLM call
    if resume and isinstance(resume.file, bytes) and resume.file.startswith(b"%PDF"):
        resume_text = await extract_text_from_pdf_bytes(resume.file)
        sys_prompt = resume_based_question_prompt(resume_count)
        resume_task = _call_llm(
            model=settings.OLLAMA_MODEL,
            system_prompt=sys_prompt,
            user_content=f"Resume Text:\n{resume_text}",
            schema=GenrateQuestions,
        )
    else:
        logger.warning(f"Invalid or missing resume for application {job_application_id}")

    # Prepare JD LLM call
    if job:
        jd_content = (
            f"Job Description: {job.description or 'Not specified'}\n"
            f"Category: {job.category or 'Not specified'}\n"
            f"Required Skills: {', '.join(job.required_skills or []) or 'Not specified'}\n"
            f"Minimum Experience: {job.min_experience or 'Not specified'} years"
        )
        sys_prompt = jd_based_question_prompt(jd_count)
        jd_task = _call_llm(
            model=settings.OLLAMA_MODEL,
            system_prompt=sys_prompt,
            user_content=jd_content,
            schema=GenrateQuestions,
        )
    else:
        logger.warning(f"Job posting not found for application {job_application_id}")

    # Run both LLM calls in parallel if available
    results = await asyncio.gather(resume_task, jd_task, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            logger.error(f"LLM generation error: {result}")
        elif result:
            questions.extend(result.questions)

    if not questions:
        raise HTTPException(
            status_code=400,
            detail="No questions could be generated. Ensure resume and job details are valid."
        )

    return questions


async def evaluate_answer(
    question: str,
    answer: str,
    resume_context: Optional[str] = None,
) -> AnswerEval:
    """
    Evaluate and score a candidate's answer, optionally using their resume context.

    For the first two questions (Q1, Q2), resume context may be passed to provide
    additional background. Subsequent questions are evaluated without context.

    Parameters:
        question (str): The interview question being evaluated.
        answer (str): The candidate's response text.
        resume_context (str, optional): Full text of the candidate's resume if available.

    Returns:
        AnswerEval: A Pydantic schema including `score`, `analysis`, and `reason`.

    Raises:
        HTTPException(503): If the LLM evaluation call fails.
    """
    if resume_context:
        sys_prompt = resume_based_answer_evaluation_prompt()
        user_txt = f"Resume Text:\n{resume_context}\nQuestion: {question}\nAnswer: {answer}"
    else:
        sys_prompt = answer_evaluation_prompt()
        user_txt = f"Question: {question}\nAnswer: {answer}"
    return await _call_llm(
        model=settings.OLLAMA_MODEL,
        system_prompt=sys_prompt,
        user_content=user_txt,
        schema=AnswerEval,
    )


async def handle_complete_interview_analysis(responses: List[dict]) -> dict:
    """
    Aggregate individual question evaluations, compute a weighted overall score,
    and generate a comprehensive interview analysis via the LLM.

    The weighting formula is:
      - Q1: 10%
      - Q2: 20%
      - Q3–Q5: 70% (average of their scores)

    Parameters:
        responses (List[dict]): List of 5 dicts, each containing fields from
                                InterviewQuestionResponse after scoring.

    Returns:
        dict: {
            "analysis": dict from FullInterviewAnalysis,
            "overall_score_out_of_5": float (0–5)
        }

    Raises:
        HTTPException(400): If not exactly 5 responses or scores out of range.
    """
    if len(responses) != 5:
        raise HTTPException(status_code=400, detail="Exactly 5 question responses required")
    scores = [r["individual_score"] for r in responses]
    if any(s < 0 or s > 5 for s in scores):
        raise HTTPException(status_code=400, detail="Scores must be between 0 and 5")

    overall = round(0.1 * scores[0] + 0.2 * scores[1] + 0.7 * (sum(scores[2:]) / 3), 2)

    transcript = "\n".join(
        f"QID:{r['question_id']} | Score:{r['individual_score']} | Reason:{r['reason_for_score_given']}\nAnalysis:{r['individual_analysis']}"
        for r in responses
    )

    sys_prompt = full_interview_analysis_prompt()
    analysis = await _call_llm(
        model=settings.OLLAMA_MODEL, system_prompt=sys_prompt, user_content=transcript, schema=FullInterviewAnalysis
    )
    analysis_data = analysis.model_dump()
    analysis_data.pop("overall_score_out_of_5", None)
    return {"analysis": analysis_data, "overall_score_out_of_5": overall}


async def store_complete_interview_analysis(
    db: AsyncSession, payload: StoreCompleteInterviewRequest
) -> dict:
    """
    Evaluate all stored interview responses, save detailed feedback to the database,
    and update the candidate's application status based on overall performance.

    Steps:
      1. Load the InterviewSession by `payload.session_id`.
      2. Fetch all InterviewQuestionResponse rows for that session.
      3. Call LLM in parallel to evaluate answers (with resume context for Q1/Q2).
      4. Update each response's score, analysis, and reason.
      5. Commit updates and generate full feedback summary.
      6. Insert InterviewFeedback.
      7. Update JobApplication status (Shortlisted/Rejected).

    Returns:
        dict: {"feedback_id": UUID, ...output from handle_complete_interview_analysis}
    """
    session_query = await db.execute(
        select(InterviewSession)
        .options(
            selectinload(InterviewSession.job_application)
            .selectinload(JobApplication.resume_version)
        )
        .where(InterviewSession.session_id == payload.session_id)
    )
    session = session_query.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    interview_records = await db.execute(
        select(InterviewQuestionResponse).where(
            InterviewQuestionResponse.session_id == payload.session_id
        )
    )
    records = interview_records.scalars().all()
    if not records:
        raise HTTPException(status_code=404, detail="No responses found")

    resume_text = None
    if any(r.question_id in ("Q1", "Q2") for r in records):
        try:
            resume_bytes = session.job_application.resume_version.file
            resume_text = await extract_text_from_pdf_bytes(resume_bytes)
        except Exception as e:
            logger.exception(f"Failed to extract resume text : {str(e)}")
            raise HTTPException(status_code=400, detail="Could not extract resume text.")

    try:
        tasks = []
        for rec in records:
            if rec.question_id in ("Q1", "Q2"):
                tasks.append(evaluate_answer(rec.question, rec.user_answer, resume_text))
            else:
                tasks.append(evaluate_answer(rec.question, rec.user_answer))
        results = await asyncio.gather(*tasks)
    except Exception as e:
        logger.exception(f"Failed during LLM evaluations : {str(e)}")
        raise HTTPException(status_code=503, detail="Answer evaluation failed.")

    # Apply evaluation results to each record
    for rec, eval_result in zip(records, results):
        rec.individual_score = eval_result.score
        rec.individual_analysis = eval_result.answer_analysis
        rec.reason_for_score_given = eval_result.reason

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.exception(f"Failed to commit evaluated responses : {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to store evaluated answers")

    # Handle overall interview analysis
    combined = await handle_complete_interview_analysis([
        {
            "question_id": rec.question_id,
            "individual_score": rec.individual_score,
            "individual_analysis": rec.individual_analysis,
            "reason_for_score_given": rec.reason_for_score_given,
        }
        for rec in records
    ])

    feedback = InterviewFeedback(
        feedback_id=uuid4(),
        session_id=session.session_id,
        job_id=session.job_application.job_id,
        feedback_type=FeedbackType.L1,
        overall_score_out_of_5=combined["overall_score_out_of_5"],
        strengths_of_candidate=combined["analysis"].get("strengths_of_candidate", []),
        areas_of_improvement=combined["analysis"].get("areas_of_improvement", []),
        feedback_summary=combined["analysis"].get("detailed_feedback", ""),
        skill_recommendations = combined["analysis"].get("skill_recommendations",[])
    )
    db.add(feedback)

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.exception(f"Failed to commit interview feedback: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to store interview feedback.")

    # Update job application status
    try:
        app_q = await db.execute(
            select(JobApplication).where(
                JobApplication.student_id == session.job_application.student_id,
                JobApplication.job_id == session.job_application.job_id,
            )
        )
        application = app_q.scalar_one_or_none()
        if application:
            application.status = (
                JobApplicationStatus.Shortlisted
                if combined["overall_score_out_of_5"] >= settings.THRESHOLD_VALUE_L1
                else JobApplicationStatus.Rejected
            )
            await db.commit()
    except Exception as e:
        await db.rollback()
        logger.exception(f"Failed to update job application status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update application status.")

    return {"feedback_id": feedback.feedback_id, **combined}



async def create_session_with_questions(
    db: AsyncSession,
    student_id: UUID,
    questions: List[str],
    job_application_id: Optional[UUID],
    role: str,
    audio_link: Optional[str] = None,
    is_video_enabled: bool = False,
) -> dict:
    """
    Initialize a new interview session: persist session metadata and blank question rows.

    Parameters:
        db (AsyncSession): Database session.
        student_id (UUID): The candidate's student ID.
        questions (List[str]): List of interview questions to store.
        job_id (UUID, optional): Related job posting ID, if any.
        job_application_id (UUID, optional): Related application ID.
        role (str): The role or position title under interview.
        audio_link (str, optional): URL to recorded audio, if provided.
        is_video_enabled (bool): Flag indicating if video recording is active.

    Returns:
        dict: {"session_id": UUID, "questions": [{"question_id": str,"question": str}, ...]}

    Raises:
        HTTPException(500): If DB commit fails.
    """
    session = InterviewSession(
        session_id=uuid4(),
        job_application_id=job_application_id,
        student_id=student_id,
        role=role,
        questions=questions,
        audio_link=audio_link,
        is_video_enabled=is_video_enabled,
    )
    responses = []
    db.add(session)
    for idx, q in enumerate(questions, start=1):
        rec = InterviewQuestionResponse(
            response_id=uuid4(),
            session_id=session.session_id,
            question_id=f"Q{idx}",
            question=q,
        )
        db.add(rec)
        responses.append({"question_id": rec.question_id, "question": q})

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"Session creation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to store session")

    return {"session_id": str(session.session_id), "questions": responses}

async def fetch_all_l1_candidates(db: AsyncSession,job_id: UUID) -> List[ShortlistedCandidate]:
    """
    Retrieve all level-1 interview feedback entries for a job, joined with candidate info.

    Parameters:
        db (AsyncSession): Database session.
        job_id (UUID): The job posting ID to filter feedback.

    Returns:
        List[ShortlistedCandidate]: Sorted list of candidates with full name, email, score, status.

    Raises:
        None. Returns empty list if no records found.
    """
    stmt = (
        select(InterviewFeedback)
        .options(
            selectinload(InterviewFeedback.session)
            .selectinload(InterviewSession.job_application)
            .selectinload(JobApplication.student)
            .selectinload(Student.user),
        )
        .where(
            InterviewFeedback.job_id == job_id,
            InterviewFeedback.feedback_type == FeedbackType.L1,
            InterviewFeedback.session.has(
                InterviewSession.job_application.has(
                    JobApplication.status.in_([JobApplicationStatus.Shortlisted, JobApplicationStatus.Rejected])
                )
            ),
        )
    )
    rows = (await db.execute(stmt)).all()

    candidates = []
    for (f,) in rows:
        session = f.session
        application = session.job_application
        student = application.student
        user = student.user

        candidates.append(
            ShortlistedCandidate(
                full_name=user.full_name,
                email=student.email,
                score=round(f.overall_score_out_of_5 * 20, 2),
                status=application.status.value,
                user_id=user.user_id,
                strengths_of_candidate=f.strengths_of_candidate or [],
            )
        )

    return sorted(candidates, key=lambda c: c.score, reverse=True)


async def fetch_all_feedback_for_user(user_id: UUID, db: AsyncSession) -> dict:
    """
    Fetch both MOCK and L1 feedback for the given student user ID in a constant number
    of DB queries by leveraging JOINs instead of per‐item lookups.

    Parameters:
        user_id (UUID): The user ID of the student.
        db (AsyncSession): Database session.

    Returns:
        dict: {
            "MOCK": [...],
            "L1": [...]
        }

    Raises:
        HTTPException(404): If the student is not found.
    """
    # 1. Resolve student_id
    student_q = await db.execute(
        select(Student.student_id).where(Student.user_id == user_id)
    )
    student_row = student_q.scalar_one_or_none()
    if not student_row:
        raise HTTPException(status_code=404, detail="Student not found")
    student_id = student_row

    # 2. Fetch all L1 feedback + job info in one go
    l1_stmt = (
        select(
            InterviewSession.session_id,
            InterviewFeedback.feedback_id,
            InterviewFeedback.feedback_summary,
            InterviewFeedback.strengths_of_candidate,
            InterviewFeedback.areas_of_improvement,
            InterviewFeedback.overall_score_out_of_5,
            InterviewFeedback.skill_recommendations,
            InterviewFeedback.submitted_at,
            JobPosting.job_id,
            JobPosting.company_name,
            JobPosting.title,
        )
        .join(InterviewFeedback, InterviewFeedback.session_id == InterviewSession.session_id)
        .join(JobPosting, InterviewFeedback.job_id == JobPosting.job_id)
        .where(
            InterviewSession.student_id == student_id,
            InterviewFeedback.feedback_type == FeedbackType.L1,
        )
    )
    l1_rows = (await db.execute(l1_stmt)).all()

    l1_feedback = [
        {
            "session_id": str(sess_id),
            "feedback_id": str(fb_id),
            "feedback_summary": summary,
            "strengths_of_candidate": strengths or [],
            "areas_of_improvement": areas or [],
            "overall_score_out_of_5": score,
            "skill_recommendations": skills or [],
            "submitted_at": submitted_at.isoformat(),
            "job_id": str(job_id),
            "company_name": company_name,
            "title": title,
        }
        for (
            sess_id,
            fb_id,
            summary,
            strengths,
            areas,
            score,
            skills,
            submitted_at,
            job_id,
            company_name,
            title,
        ) in l1_rows
    ]
    logger.info("L1 feedback count: %d", len(l1_feedback))

    # 3. Fetch mock interview sessions in one query
    mock_stmt = select(
        MockInterviewSession.session_id,
        MockInterviewSession.score,
        MockInterviewSession.created_at,
    ).where(MockInterviewSession.student_id == student_id)

    mock_rows = (await db.execute(mock_stmt)).all()
    mock_feedback = [
        {
            "session_id": str(sid),
            "score": score,
            "created_at": created_at.isoformat(),
        }
        for sid, score, created_at in mock_rows
    ]
    logger.info("Mock feedback count: %d", len(mock_feedback))

    return {"MOCK": mock_feedback, "L1": l1_feedback}

