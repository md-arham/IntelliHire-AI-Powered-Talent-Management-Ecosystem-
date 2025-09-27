from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database.db import Base
import uuid


class JobCandidateScreening(Base):
    __tablename__ = "job_candidate_screening"

    screening_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employer_profiles.employer_id", ondelete="SET NULL"),
    )
    job_id = Column(
        UUID(as_uuid=True), ForeignKey("job_postings.job_id", ondelete="CASCADE")
    )

    employer = relationship("EmployerProfile", backref="candidate_screenings")
    job = relationship("JobPosting", backref="candidate_screenings")
