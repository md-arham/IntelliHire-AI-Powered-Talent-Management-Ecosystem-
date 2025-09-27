import uuid

from sqlalchemy import TIMESTAMP, Boolean, Column, Enum, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import BYTEA, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.db import Base
from app.database.models.enums_models import ResumeTypeEnum


class ResumeVersion(Base):
    __tablename__ = "resume_versions"

    version_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(
        UUID(as_uuid=True), ForeignKey("students.student_id", ondelete="CASCADE")
    )
    resume_name = Column(Text)
    resume_type = Column(
        Enum(ResumeTypeEnum), nullable=False
    )  # Ensure this Enum matches DB CHECK
    source_resume_id = Column(UUID(as_uuid=True), nullable=True)
    ats_score = Column(
        Float
    )  # CHECK (ats_score BETWEEN 0 AND 100) – enforce at app or DB level
    ai_feedback = Column(Text)  # Ai feedback on resume
    file = Column(BYTEA)  # Replaces file_url with binary storage
    file_path = Column(Text)  # Optional: path or metadata reference
    created_at = Column(TIMESTAMP, server_default=func.now())
    is_active = Column(Boolean, default=True)

    student = relationship("Student", backref="resume_versions")
    job_applications = relationship("JobApplication", back_populates="resume_version")
