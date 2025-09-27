from sqlalchemy import Column, Text, Float, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.sql import func
from app.database.db import Base
from sqlalchemy import Enum
from sqlalchemy.orm import relationship
import enum
import uuid


class FeedbackType(enum.Enum):
    L1 = "L1"
    MOCK = "MOCK"


class InterviewFeedback(Base):
    __tablename__ = "interview_feedback"

    feedback_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("job_postings.job_id", ondelete="CASCADE"),
        default=uuid.uuid4,
    )
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("interview_sessions.session_id", ondelete="CASCADE"),
    )
    feedback_summary = Column(Text)
    strengths_of_candidate = Column(ARRAY(Text))
    areas_of_improvement = Column(ARRAY(Text))
    overall_score_out_of_5 = Column(Float)
    skill_recommendations = Column(ARRAY(Text))
    feedback_type = Column(
        Enum(FeedbackType, name="feedback_type_enum"), nullable=False
    )
    submitted_at = Column(TIMESTAMP, server_default=func.now())
    learning_path = Column(JSONB, nullable=True)

    session = relationship("InterviewSession", back_populates="feedback_entries")
