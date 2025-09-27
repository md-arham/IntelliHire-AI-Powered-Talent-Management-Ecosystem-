from sqlalchemy import Column, String, Text, Float, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database.db import Base
import uuid


class InterviewQuestionResponse(Base):
    __tablename__ = "interview_question_responses"

    response_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("interview_sessions.session_id", ondelete="CASCADE"),
    )
    question_id = Column(String)
    question = Column(Text)
    user_answer = Column(Text)
    individual_analysis = Column(Text)
    individual_score = Column(Float)
    reason_for_score_given = Column(Text)
    created_at = Column(TIMESTAMP, server_default=func.now())
