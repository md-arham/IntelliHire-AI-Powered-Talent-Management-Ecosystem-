# app/models/student_course.py
from sqlalchemy import Column, Integer, TIMESTAMP, Text, Float
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.database.db import Base


class StudentCourse(Base):
    __tablename__ = "student_course"
    course_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), nullable=False)
    roadmap_id = Column(UUID(as_uuid=True), nullable=True)
    status = Column(Text, default="Not Started")
    progress_percent = Column(Integer, default=0)
    last_accessed = Column(TIMESTAMP, nullable=True)
    title = Column(Text, nullable=False)
    level = Column(Text, nullable=False)
    duration = Column(Text, nullable=False)
    url = Column(Text, nullable=False)
    rating = Column(Float, nullable=True)
    imageUrl = Column(Text, nullable=True)
    image = Column(Text, nullable=True)
    aspiration_name = Column(Text, nullable=True)