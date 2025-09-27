from app.database.db import Base 
from sqlalchemy import Column,Integer,String, Enum
from app.schemas.router_registration_schema import EffectEnum

class EndpointPermission(Base):
    __tablename__ = "endpoint_permissions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    role = Column(String, nullable=False, index=True)          # e.g., "user", "admin"
    domain = Column(String, nullable=False, index=True)        # e.g., "tenant:system"
    object = Column(String, nullable=False, index=True)        # e.g., "job"
    path = Column(String, nullable=False)                      # e.g., "/api/jobs/createJob"
    method = Column(String, nullable=False)                    # e.g., "GET", "POST"
    action = Column(String, nullable=False)                    # same as method; optionally used separately
    effect = Column(Enum(EffectEnum), default=EffectEnum.allow)