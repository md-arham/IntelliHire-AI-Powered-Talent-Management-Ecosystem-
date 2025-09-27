from sqlalchemy import Column, String, Text, Enum
from sqlalchemy.dialects.postgresql import UUID

from app.database.db import Base

from app.database.models.enums_models import CompanyType

import uuid
from sqlalchemy.orm import relationship


class Company(Base):
    __tablename__ = "companies"

    company_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(150), nullable=False)
    type = Column(Enum(CompanyType))
    location = Column(String(100))
    logo_url = Column(Text)
    website_url = Column(Text)
    description = Column(Text)

    drives = relationship("CampusDriveCompany", back_populates="company")
