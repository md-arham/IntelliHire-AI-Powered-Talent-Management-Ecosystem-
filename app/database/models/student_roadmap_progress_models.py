from sqlalchemy import Column, Integer, ForeignKey, Enum, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database.db import Base
from app.database.models.enums_models import RoadmapStatusEnum
import uuid


class student_roadmap_progress(Base):
    __tablename__ = "student_roadmap_progress"

    student_id = Column(
        UUID(as_uuid=True),
        ForeignKey("students.student_id", ondelete="CASCADE"),
        primary_key=True, 
        default=uuid.uuid4,
    )
    roadmap_id = Column(
        UUID(as_uuid=True),
        ForeignKey("roadmaps.roadmap_id", ondelete="CASCADE"),
        primary_key=True,
        default=uuid.uuid4,
    )
    status = Column(Enum(RoadmapStatusEnum), default=RoadmapStatusEnum.NotStarted)
    progress_percent = Column(Integer, default=0)
    followed_at = Column(TIMESTAMP, server_default=func.now())


# CREATE TABLE student_roadmap (
# 	roadmap_id UUID PRIMARY KEY,
#    student_id UUID REFERENCES students(student_id) ON DELETE CASCADE,
#    status VARCHAR(20) CHECK (status IN ('Not Started', 'In Progress', 'Completed')) DEFAULT 'Not Started',
#    progress_percent INT DEFAULT 0,
#    followed_at TIMESTAMP DEFAULT NOW(),
# );
