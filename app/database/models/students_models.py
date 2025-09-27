from sqlalchemy import Column, ForeignKey, String, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.database.db import Base
from sqlalchemy.sql import func


class Student(Base):
    __tablename__ = "students"

    student_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    college_id = Column(UUID(as_uuid=True), ForeignKey("colleges.college_id"))
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE")
    )
    email = Column(String(100), unique=True, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    batch_id = Column(
        UUID(as_uuid=True), ForeignKey("student_batches.batch_id"), nullable=True
    )

    user = relationship("User", back_populates="student_profile")
    aspirations = relationship(
        "Aspiration", back_populates="student", cascade="all, delete-orphan"
    )
    college = relationship("College", back_populates="students")
    batch = relationship("StudentBatch", back_populates="students")
    applications = relationship("JobApplication", back_populates="student")
    recommended_jobs = relationship("RecommendedJob", back_populates="student")
    mock_interview_sessions = relationship(
        "MockInterviewSession",
        back_populates="student",
        cascade="all, delete-orphan",
        uselist=True,
    )
