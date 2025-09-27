from sqlalchemy import Column, Float, TIMESTAMP, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.db import Base
import uuid


class StudentInsight(Base):
    __tablename__ = "student_insights"

    insight_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(
        UUID(as_uuid=True), ForeignKey("students.student_id", ondelete="CASCADE")
    )
    recommended_roles = Column(ARRAY(Text))
    most_matched_skills = Column(ARRAY(Text))
    skill_gap_areas = Column(ARRAY(Text))
    learning_recommendations = Column(ARRAY(Text))
    engagement_score = Column(Float)
    last_updated = Column(TIMESTAMP, server_default=func.now())

    student = relationship("Student", backref="insights")
