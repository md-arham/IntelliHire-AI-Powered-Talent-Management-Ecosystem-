from sqlalchemy import Column, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database.db import Base
import uuid


class EmployerProfile(Base):
    __tablename__ = "employer_profiles"

    employer_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE")
    )
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.company_id"))
    created_at = Column(TIMESTAMP, server_default=func.now())

    user = relationship("User", back_populates="employer_profile")
    company = relationship("Company")
    employer_resumes = relationship("EmployerResume", back_populates="employer_profile", cascade="all, delete-orphan")
