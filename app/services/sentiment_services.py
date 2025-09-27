from app.database.models.job_postings_models import JobPosting
from fastapi import HTTPException
from app.utils.settings import sentiment_tokenizer,sentiment_model
import torch
import uuid
from app.database.models.sentiment_models import InterviewFeedbackSentiment, SentimentLabel
from app.database.models.interview_expirence_feedback_models import InterviewExperienceFeedback
from app.database.models.interview_sessions_models import InterviewSession
from app.utils.logger_config import logger
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError



async def get_feedback_text_for_sentiment(db: AsyncSession, feedback_id: str) -> str:
    """
    Fetches feedback by ID and formats relevant fields into a structured text block 
    for sentiment analysis.

    Args:
        db (AsyncSession): SQLAlchemy async session.
        feedback_id (str): UUID of the feedback entry.

    Returns:
        str: Multi-line formatted feedback string for sentiment analysis.

    Raises:
        ValueError: If no feedback is found.
    """
    try:
        result = await db.execute(
            select(InterviewExperienceFeedback).where(
                InterviewExperienceFeedback.feedback_id == feedback_id
            )
        )
        feedback = result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error fetching feedback by ID {feedback_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch feedback from database")
    if not feedback:
        raise ValueError(f"No feedback found with ID {feedback_id}")

    formatted_text = (
        f"Overall Experience: {feedback.overall_experience.value}\n"
        f"Question Relevance: {feedback.question_relevance.value}\n"
        f"Question Clarity: {feedback.question_clarity.value}\n"
        f"Ease of Use: {feedback.ease_of_use.value}\n"
        f"Suggestions: {feedback.suggestions or 'None'}"
    )

    return formatted_text


async def compute_sentiment_with_scores(text: str):
    try:
        inputs = sentiment_tokenizer(text, return_tensors="pt")
        labels = ['negative', 'neutral', 'positive']
        with torch.no_grad():
            logits = sentiment_model(**inputs).logits
        probs = torch.nn.functional.softmax(logits, dim=1).squeeze().tolist()

        # Get index of highest probability
        max_idx = int(torch.argmax(torch.tensor(probs)))
        sentiment_label = labels[max_idx]

        return sentiment_label, probs  # e.g., 'neutral', [0.1, 0.7, 0.2]
    except Exception as e:
        logger.error(f"Sentiment analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Sentiment model inference failed")



async def store_feedback_sentiment(
    db: AsyncSession,
    feedback_id: uuid.UUID,
    session_id: uuid.UUID,
    job_id: uuid.UUID
):
    """
    Stores the sentiment analysis result of a feedback entry into the database.

    This function fetches the corresponding interview session to retrieve the student ID,
    generates a combined feedback text for sentiment analysis, computes the sentiment label
    and score, and stores the result in the InterviewFeedbackSentiment table.

    Args:
        db (AsyncSession): SQLAlchemy async session.
        feedback_id (uuid.UUID): UUID of the feedback entry to analyze.
        session_id (uuid.UUID): UUID of the interview session.
        job_id (uuid.UUID): UUID of the associated job posting.

    Returns:
        dict: A dictionary containing the sentiment label and sentiment score.

    Raises:
        HTTPException: If the interview session is not found or if storing the result fails.
    """

    logger.info("Storing sentiments.")
    try:
        # Fetch the interview session
        result = await db.execute(select(InterviewSession).where(InterviewSession.session_id == session_id))
        session = result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error fetching interview session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch interview session")

    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found")

    student_id = session.student_id
    try:
    # Prepare text and perform sentiment analysis
        combined_text = await get_feedback_text_for_sentiment(db, str(feedback_id))
        sentiment_str, sentiment_scores = await compute_sentiment_with_scores(combined_text)
    except HTTPException:
        raise  # propagate known HTTPExceptions
    except Exception as e:
        logger.error(f"Failed to compute sentiment for feedback {feedback_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute sentiment")
    sentiment_enum = SentimentLabel(sentiment_str)

    # Create sentiment record
    sentiment_entry = InterviewFeedbackSentiment(
        sentiment_id=uuid.uuid4(),
        feedback_id=feedback_id,
        session_id=session_id,
        student_id=student_id,
        job_id=job_id,
        sentiment=sentiment_enum,
        sentiment_score=sentiment_scores,
    )

    try:
        db.add(sentiment_entry)
        await db.commit()
        logger.info("Committed to DB.")
        return {
            "sentiment": sentiment_str,
            "sentiment_score": sentiment_scores
        }
    except Exception as e:
        await db.rollback()
        logger.error(f"DB commit failed for sentiment entry: {e}")
        raise HTTPException(status_code=500, detail="Error storing sentiment to database")


async def get_latest_sentiment_data(db: AsyncSession, student_id: uuid.UUID):
    try:
        # Get latest sentiment entry
        result = await db.execute(
            select(InterviewFeedbackSentiment)
            .where(InterviewFeedbackSentiment.student_id == student_id)
            .order_by(desc(InterviewFeedbackSentiment.created_at))
        )
        latest_entry = result.scalars().first()
    except SQLAlchemyError as e:
        logger.error(f"Failed to fetch latest sentiment entry: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch latest sentiment data")

    if not latest_entry:
        return None
    try:
        # Get associated job details
        job_result = await db.execute(
            select(JobPosting)
            .where(JobPosting.job_id == latest_entry.job_id)
        )
        job = job_result.scalars().first()
    except SQLAlchemyError as e:
        logger.error(f"Failed to fetch job details for sentiment entry: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch job details")
    
    sentiment_index = {
        "negative": 0,
        "neutral": 1,
        "positive": 2
    }[latest_entry.sentiment.value]

    sentiment_score = latest_entry.sentiment_score[sentiment_index]

    return {
        "sentiment": latest_entry.sentiment.value,
        "score": round(sentiment_score,4)*100,
        "job_details": {
            "title": job.title if job else "Unknown",
            "company_name": job.company_name if job else "Unknown",
            "location": job.location if job else "Unknown",
            "job_category_type": job.job_category_type if job else None,
            "posted_at": job.posted_at if job else None,
        },
        "created_at": latest_entry.created_at.date().isoformat(),
    }


async def get_grouped_trends_by_sentiment(db: AsyncSession, student_id: uuid.UUID):
    '''
    sentiment based on the feedback given by the student for interviews
    '''
    try:
        # Fetch sentiment history (async)
        history_result = await db.execute(
            select(InterviewFeedbackSentiment)
            .where(InterviewFeedbackSentiment.student_id == student_id)
            .order_by(InterviewFeedbackSentiment.created_at)
        )
        history = history_result.scalars().all()
    except SQLAlchemyError as e:
        logger.error(f"Failed to fetch sentiment history: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch sentiment trend data")


    trends = {
        "positive_trend": [],
        "neutral_trend": [],
        "negative_trend": [],
    }

    sentiment_score_index = {
        "negative": 0,
        "neutral": 1,
        "positive": 2,
    }

    for entry in history:
        sentiment = entry.sentiment.value
        index = sentiment_score_index.get(sentiment)
        score = (
            entry.sentiment_score[index]
            if index is not None and len(entry.sentiment_score) > index
            else None
        )
        try:
            # Async job details fetch
            job_result = await db.execute(
                select(JobPosting).where(JobPosting.job_id == entry.job_id)
            )
            job = job_result.scalars().first()
        except SQLAlchemyError as e:
            logger.error(f"Failed to fetch job details for entry {entry.id}: {e}")
            job = None
        label = f"{job.title} - {job.company_name}" if job else "Unknown"

        trends[f"{sentiment}_trend"].append({
            "x_axis": entry.created_at.date().isoformat(),
            "y_axis": score,
            "legend": label,
        })

    return trends