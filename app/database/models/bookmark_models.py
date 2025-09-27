import uuid
from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database.db import Base
from app.database.models.job_postings_models import JobPosting
from app.database.models.students_models import Student

class Bookmark(Base):
    __tablename__ = "bookmark"

    bookmark_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("job_postings.job_id", ondelete="CASCADE"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.student_id", ondelete="CASCADE"), nullable=False)

    # Relationships for easier querying
    job = relationship("JobPosting", back_populates="bookmarks")
    student = relationship("Student", back_populates="bookmarks")
    
JobPosting.bookmarks = relationship("Bookmark", back_populates="job", cascade="all, delete-orphan")
Student.bookmarks = relationship("Bookmark", back_populates="student", cascade="all, delete-orphan")