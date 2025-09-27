from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.database.db import Base
import uuid

# class roadmaps(Base):
#     __tablename__ = "roadmaps"


#     roadmap_id = Column(UUID(as_uuid=True), primary_key=True)
#     role = Column(String(100))
#     data = Column(JSONB )

"""
CREATE TABLE roadmaps (
    roadmap_id UUID PRIMARY KEY,
    student_id UUID REFERENCES students(student_id) ON DELETE CASCADE,
    role VARCHAR(100),
    data JSONB,
);
"""


class Roadmaps(Base):
    __tablename__ = "roadmaps"

    roadmap_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(
        UUID(as_uuid=True), ForeignKey("students.student_id", ondelete="CASCADE")
    )
    role = Column(String(100))
    data = Column(JSONB)
