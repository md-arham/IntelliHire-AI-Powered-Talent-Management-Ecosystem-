import uuid

from sqlalchemy import TIMESTAMP, Boolean, Column, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.db import Base


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    session_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_application_id = Column(
        UUID(as_uuid=True),
        ForeignKey("job_applications.application_id", ondelete="CASCADE"),
        nullable=False,
    )

    student_id = Column(
        UUID(as_uuid=True), ForeignKey("students.student_id", ondelete="CASCADE")
    )
    role = Column(String(100))
    questions = Column(JSONB)
    responses = Column(JSONB)
    audio_link = Column(Text)
    is_video_enabled = Column(Boolean, default=False)
    score = Column(Float)
    feedback = Column(JSONB)
    created_at = Column(TIMESTAMP, server_default=func.now())

    student = relationship("Student", backref="interview_sessions")
    feedback_entries = relationship(
        "InterviewFeedback", back_populates="session", cascade="all, delete-orphan"
    )
    question_responses = relationship(
        "InterviewQuestionResponse", backref="session", cascade="all, delete-orphan"
    )
    job_application = relationship(
        "JobApplication", back_populates="interview_sessions"
    )


class InterviewTerminationLog(Base):
    __tablename__ = "interview_termination_logs"

    log_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # FK to interview session
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("interview_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )

    # FK to student (optional but helpful for faster filtering)
    student_id = Column(
        UUID(as_uuid=True),
        ForeignKey("students.student_id", ondelete="CASCADE"),
        nullable=False,
    )

    reason = Column(String(255), nullable=False)  # "No person detected", etc.
    timestamp = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    # Relationships
    session = relationship(
        "InterviewSession", backref="termination_logs", lazy="selectin"
    )
    student = relationship("Student", backref="termination_logs", lazy="selectin")
