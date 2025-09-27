from sqlalchemy import Column, Float, Boolean, TIMESTAMP, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.db import Base
import uuid


class ResumeScreeningResult(Base):
    __tablename__ = "resume_screening_results"

    screening_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id = Column(
        UUID(as_uuid=True), ForeignKey("resume_versions.version_id", ondelete="CASCADE")
    )
    student_id = Column(
        UUID(as_uuid=True), ForeignKey("students.student_id", ondelete="CASCADE")
    )
    is_qualified = Column(Boolean)
    screened_at = Column(TIMESTAMP, server_default=func.now())

    student = relationship("Student", backref="screening_results")
    version = relationship("ResumeVersion", backref="screening_results")
