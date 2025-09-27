from sqlalchemy import (
    Column,
    Enum as SqlEnum,
    ARRAY,
    TIMESTAMP,
    ForeignKey,
    Float,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.ext.mutable import MutableList
from app.database.db import Base
import enum
import uuid


class SentimentLabel(enum.Enum):
    positive = "positive"
    neutral = "neutral"
    negative = "negative"


class InterviewFeedbackSentiment(Base):
    __tablename__ = "interview_feedback_sentiment"

    sentiment_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feedback_id = Column(
        UUID(as_uuid=True),
        ForeignKey("interview_experience_feedback.feedback_id", ondelete="CASCADE"),
    )
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("interview_sessions.session_id", ondelete="CASCADE"),
    )
    job_id = Column(
        UUID(as_uuid=True), ForeignKey("job_postings.job_id", ondelete="SET NULL")
    )
    student_id = Column(
        UUID(as_uuid=True), ForeignKey("students.student_id", ondelete="CASCADE")
    )

    sentiment = Column(
        SqlEnum(SentimentLabel, name="sentiment_label_enum"), nullable=False
    )
    sentiment_score = Column(MutableList.as_mutable(ARRAY(Float)), nullable=False)

    created_at = Column(TIMESTAMP, server_default=func.now())
