import uuid

from sqlalchemy import Column, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.db import Base


class Aspiration(Base):
    __tablename__ = "aspirations"

    aspiration_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.student_id", ondelete="CASCADE"))
    aspiration_text = Column(Text, nullable=False)

    student = relationship("Student", back_populates="aspirations")
 