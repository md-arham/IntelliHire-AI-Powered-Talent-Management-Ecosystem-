from sqlalchemy import Column, String, Text, Enum
from sqlalchemy.dialects.postgresql import UUID

from app.database.db import Base
from app.database.models.enums_models import CourseLevelEnum
import uuid

class Course(Base):
    __tablename__ = "courses"
    
    course_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(150), nullable=False)
    description = Column(Text)
    category = Column(String(100))
    level = Column(Enum(CourseLevelEnum))
    duration = Column(String(50))
    url = Column(Text)
    