from sqlalchemy import Column, String, DateTime
from datetime import datetime, timezone
from app.database.db import Base



class PolicyVersion(Base):
    __tablename__ = "policy_versions"
    
    tenant = Column(String, primary_key=True)
    version = Column(String, nullable=False)
    last_updated = Column(DateTime(timezone=True), default=datetime.now(timezone.utc), nullable=False)