import uuid

from sqlalchemy import Column, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.db import Base

class CasbinRule(Base):
    """Model for storing Casbin rules"""
    __tablename__ = "casbin_rule"
   
    id = Column(Integer, primary_key=True, autoincrement=True)
    ptype = Column(String, nullable=False)
    v0 = Column(String)  # subject or role
    v1 = Column(String)  # domain or role
    v2 = Column(String)  # object
    v3 = Column(String)  # action
    v4 = Column(String)  # effect
    v5 = Column(String)  # additional info
 