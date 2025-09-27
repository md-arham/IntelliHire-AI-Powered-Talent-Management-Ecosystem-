import uuid

from sqlalchemy import TIMESTAMP, Boolean, Column, Enum, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.db import Base
from app.database.models.enums_models import JobApplicationStatus


class JobApplication(Base):
    __tablename__ = "job_applications"

    application_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(
        UUID(as_uuid=True), ForeignKey("job_postings.job_id", ondelete="CASCADE")
    )
    student_id = Column(
        UUID(as_uuid=True), ForeignKey("students.student_id", ondelete="CASCADE")
    )
    resume_version_id = Column(
        UUID(as_uuid=True), ForeignKey("resume_versions.version_id", ondelete="CASCADE")
    )
    is_campus_drive = Column(Boolean, default=False)
    status = Column(Enum(JobApplicationStatus), nullable=False)
    applied_on = Column(TIMESTAMP, server_default=func.now())
    current_stage = Column(String(50))
    fitment_score = Column(Float)
    last_updated = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    student = relationship("Student", back_populates="applications")
    job = relationship("JobPosting")
    interview_sessions = relationship("InterviewSession",back_populates="job_application")
    resume_version = relationship("ResumeVersion", back_populates="job_applications")

