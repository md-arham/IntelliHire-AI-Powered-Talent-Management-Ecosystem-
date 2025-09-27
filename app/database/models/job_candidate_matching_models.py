from sqlalchemy import Column, Float, Text, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from app.database.db import Base
import uuid


class JobCandidateMatching(Base):
    __tablename__ = "job_candidate_matching"

    screening_id = Column(
        UUID(as_uuid=True),
        ForeignKey("job_candidate_screening.screening_id", ondelete="CASCADE"),
        primary_key=True,
        default=uuid.uuid4,
    )
    student_id = Column(
        UUID(as_uuid=True),
        ForeignKey("students.student_id", ondelete="CASCADE"),
        primary_key=True,
    )
    version_id = Column(
        UUID(as_uuid=True), ForeignKey("resume_versions.version_id", ondelete="CASCADE")
    )
    matching_score = Column(Float)
    matching_skills = Column(ARRAY(Text), nullable=True)
    missing_skills = Column(ARRAY(Text), nullable=True)
    degree_qualification = Column(Text)
    college_name = Column(Text)
    branch = Column(Text)
    passed_out_year = Column(Integer)
    grade = Column(Float)
    college_type = Column(Text)
    location = Column(Text)

    screening = relationship("JobCandidateScreening", backref="matches")
    student = relationship("Student", backref="job_matchings")
