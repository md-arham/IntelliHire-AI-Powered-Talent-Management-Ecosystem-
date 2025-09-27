from sqlalchemy import (
    Column,
    String,
    Text,
    Date,
    Boolean,
    ForeignKey,
    TIMESTAMP,
    Enum,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import enum

from app.database.db import Base
from app.database.models.enums_models import (
    JobType,
    InternshipType,
)


class JobOriginType(str, enum.Enum):
    INTERNAL = "internal"  # via platform's CRUD API
    EXTERNAL = "external"  # via external scraping/API


class JobCategoryType(str, enum.Enum):
    JOB = "job"
    INTERNSHIP = "internship"


class JobPosting(Base):
    __tablename__ = "job_postings"

    job_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Source metadata
    job_origin = Column(Enum(JobOriginType, name="job_origin_enum"), nullable=False)
    job_category_type = Column(
        Enum(JobCategoryType, name="job_category_enum"), nullable=False
    )
    fetched_at = Column(
        TIMESTAMP, nullable=True, server_default=func.now()
    )  # only for external jobs

    # Common fields
    employer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employer_profiles.employer_id", ondelete="SET NULL"),
    )
    company_name = Column(Text)
    title = Column(Text, nullable=False)
    description = Column(Text)
    location = Column(Text)
    category = Column(String(100))
    application_deadline = Column(Date)
    additional_info = Column(JSONB)
    is_active = Column(Boolean, default=True)
    posted_at = Column(TIMESTAMP, server_default=func.now())

    # Internal-specific
    job_type = Column(Enum(JobType, name="job_type_enum"), nullable=True)
    required_skills = Column(ARRAY(Text))
    min_experience = Column(Text)
    salary_range = Column(Text)

    # External-specific (from internship data)
    internship_type = Column(
        Enum(InternshipType, name="internship_type_enum"), nullable=True
    )
    stipend = Column(Text)
    role = Column(String(100))
    responsibilities = Column(Text)
    requirements = Column(Text)

    employer_profile = relationship(
        "EmployerProfile", backref="job_postings", foreign_keys=[employer_id]
    )
    employer_resume_matchings = relationship(
        "EmployerResumeMatching",
        back_populates="job_posting",
        cascade="all, delete-orphan",
    )
    campus_placements = relationship("CampusPlacement", back_populates="job")
