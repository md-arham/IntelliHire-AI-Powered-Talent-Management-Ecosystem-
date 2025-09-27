from sqlalchemy import Column, ForeignKey, Enum, Integer, TIMESTAMP
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from app.database.db import Base
from app.database.models.enums_models import CourseStatusEnum
import uuid


class StudentCourseProgress(Base):
    __tablename__ = "student_course_progress"

    student_id = Column(
        UUID(as_uuid=True),
        ForeignKey("students.student_id", ondelete="CASCADE"),
        primary_key=True,
        default=uuid.uuid4,
    )
    course_id = Column(
        UUID(as_uuid=True),
        ForeignKey("courses.course_id", ondelete="CASCADE"),
        primary_key=True,
        default=uuid.uuid4,
    )
    status = Column(Enum(CourseStatusEnum), default=CourseStatusEnum.NotStarted)
    progress_percent = Column(Integer, default=0)
    last_accessed = Column(TIMESTAMP, default=func.now())
