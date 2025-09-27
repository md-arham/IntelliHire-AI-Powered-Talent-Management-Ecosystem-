from sqlalchemy import Column, Text, TIMESTAMP, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database.db import Base
import enum
import uuid


class ExperienceRating(enum.Enum):
    Excellent = "Excellent"
    Good = "Good"
    Average = "Average"
    Poor = "Poor"


class RelevanceRating(enum.Enum):
    VeryRelevant = "VeryRelevant"
    SomewhatRelevant = "SomewhatRelevant"
    NotRelevant = "NotRelevant"


class ClarityRating(enum.Enum):
    Yes = "Yes"
    Somewhat = "Somewhat"
    No = "No"


class EaseOfUseRating(enum.Enum):
    VeryEasy = "VeryEasy"
    Easy = "Easy"
    Difficult = "Difficult"
    VeryDifficult = "VeryDifficult"


class InterviewExperienceFeedback(Base):
    __tablename__ = "interview_experience_feedback"

    feedback_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("interview_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    overall_experience = Column(
        Enum(ExperienceRating, name="experience_rating_enum"), nullable=False
    )
    question_relevance = Column(
        Enum(RelevanceRating, name="relevance_rating_enum"), nullable=False
    )
    question_clarity = Column(
        Enum(ClarityRating, name="clarity_rating_enum"), nullable=False
    )
    ease_of_use = Column(
        Enum(EaseOfUseRating, name="ease_of_use_rating_enum"), nullable=False
    )
    suggestions = Column(Text)
    submitted_at = Column(TIMESTAMP, server_default=func.now())
