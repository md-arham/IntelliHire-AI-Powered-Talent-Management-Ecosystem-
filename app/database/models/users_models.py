from sqlalchemy import Column, String, Text, TIMESTAMP, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.schemas.auth_schemas import UserRole
from app.database.db import Base
import uuid


class User(Base):
    __tablename__ = "users"

    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(100), unique=True, nullable=False)
    full_name = Column(String(100), nullable= False)
    password_hash = Column(Text, nullable=True)
    role = Column(Enum(UserRole), nullable=False)
    profile_img_path = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

    placement_officer_profile = relationship(
        "CampusPlacementOfficer", uselist=False, back_populates="user"
    )
    student_profile = relationship("Student", uselist=False, back_populates="user")
    employer_profile = relationship(
        "EmployerProfile", uselist=False, back_populates="user"
    )
