from sqlalchemy import (
    Column,
    TIMESTAMP,
    Boolean,
    ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database.db import Base

class TimeSlot(Base):
    __tablename__ = "time_slots"

    slot_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("job_postings.job_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employer_profiles.employer_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    start_time = Column(TIMESTAMP, nullable=False)
    end_time = Column(TIMESTAMP, nullable=False)
    is_booked = Column(Boolean, default=False)
    booked_by = Column(
        UUID(as_uuid=True),
        ForeignKey("students.student_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())