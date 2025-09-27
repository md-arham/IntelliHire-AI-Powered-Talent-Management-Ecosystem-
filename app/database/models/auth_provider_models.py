from enum import Enum
from uuid import uuid4

from sqlalchemy import Column, ForeignKey, String, TIMESTAMP
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database.db import Base


class AuthProviderEnum(str, Enum):
    GOOGLE = "google"
    LINKEDIN = "linkedin"
    # You can add more here


class UserAuthProvider(Base):
    __tablename__ = "user_auth_providers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE")
    )
    provider = Column(SQLEnum(AuthProviderEnum), nullable=False)
    provider_user_id = Column(String, nullable=False, unique=True)

    user = relationship("User", backref="auth_providers")


class OTPStore(Base):
    __tablename__ = "otp_store"

    otp = Column(String, primary_key=True)
    email = Column(String, nullable=False)
    otp_secret = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    