from sqlalchemy import Column, ForeignKey, Float, Text
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from app.database.db import Base
import uuid


class ResumeScreeningInternship(Base):
    __tablename__ = "resume_screening_internship"

    screening_id = Column(
        UUID(as_uuid=True),
        ForeignKey("resume_screening_results.screening_id", ondelete="CASCADE"),
        primary_key=True,
        default=uuid.uuid4,
    )
    internship_id = Column(UUID(as_uuid=True), primary_key=True)
    matching_score = Column(Float, nullable=True)  
    matching_skills = Column(ARRAY(Text), nullable=True)
    missing_skills = Column(ARRAY(Text), nullable=True)
    source = Column(Text)
