from sqlalchemy import (
    UUID,
    Column,
    String,
    ForeignKey,
    DateTime,
    Text,
    Boolean,
    func,
    Integer,
)
from sqlalchemy.orm import relationship

from app.database.db import Base

import uuid


class College(Base):
    __tablename__ = "colleges"

    college_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    location = Column(String(255))
    affiliated_university = Column(String(255))

    placements = relationship("CampusPlacement", back_populates="college")
    students = relationship("Student", back_populates="college")
    resources = relationship("PlacementResource", back_populates="college")
    batches = relationship("StudentBatch", back_populates="college")
    placement_officers = relationship(
        "CampusPlacementOfficer", back_populates="college"
    )
    drives = relationship("CampusDrive", back_populates="college")


class CampusPlacementOfficer(Base):
    __tablename__ = "campus_placement_officers"

    officer_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False, unique=True
    )
    college_id = Column(
        UUID(as_uuid=True), ForeignKey("colleges.college_id"), nullable=False
    )
    contact_detail = Column(String(255))
    joined_at = Column(DateTime, default=func.now())

    user = relationship("User", back_populates="placement_officer_profile")
    college = relationship("College", back_populates="placement_officers")


class CampusPlacement(Base):
    __tablename__ = "campus_placements"

    placement_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    drive_id = Column(
        UUID(as_uuid=True), ForeignKey("campus_drives.drive_id"), nullable=False
    )
    job_id = Column(
        UUID(as_uuid=True), ForeignKey("job_postings.job_id"), nullable=False
    )
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.company_id"))
    college_id = Column(UUID(as_uuid=True), ForeignKey("colleges.college_id"))

    drive_date = Column(DateTime, default=DateTime)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=DateTime)

    # Optional relationship for easier joins
    drive = relationship("CampusDrive", back_populates="placements")
    job = relationship("JobPosting", back_populates="campus_placements")
    college = relationship("College", back_populates="placements")


class RecommendedJob(Base):
    __tablename__ = "recommended_jobs"

    recommendation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(
        UUID(as_uuid=True), ForeignKey("students.student_id"), nullable=False
    )
    job_id = Column(
        UUID(as_uuid=True), ForeignKey("job_postings.job_id"), nullable=False
    )
    recommended_by_officer_id = Column(
        UUID(as_uuid=True), ForeignKey("campus_placement_officers.officer_id")
    )

    recommended_by_officer = relationship("CampusPlacementOfficer")
    student = relationship("Student", back_populates="recommended_jobs")


class PlacementResource(Base):
    __tablename__ = "placement_resources"

    resource_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    uploaded_by_officer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("campus_placement_officers.officer_id"),
        nullable=False,
    )
    college_id = Column(
        UUID(as_uuid=True), ForeignKey("colleges.college_id"), nullable=False
    )
    title = Column(String(255))
    description = Column(Text)
    file_path = Column(Text)
    created_at = Column(DateTime, default=func.now())

    college = relationship("College", back_populates="resources")
    uploaded_by_officer = relationship("CampusPlacementOfficer")


class StudentBatch(Base):
    __tablename__ = "student_batches"

    batch_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    college_id = Column(
        UUID(as_uuid=True), ForeignKey("colleges.college_id"), nullable=False
    )
    batch_year = Column(Integer, nullable=False)  # e.g., 2024
    department = Column(String(100))  # Optional: e.g., "CSE", "ECE", etc.
    section = Column(String(50))  # Optional
    created_at = Column(DateTime, default=func.now())

    college = relationship("College", back_populates="batches")
    students = relationship("Student", back_populates="batch")


class CampusDrive(Base):
    __tablename__ = "campus_drives"

    drive_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    college_id = Column(
        UUID(as_uuid=True), ForeignKey("colleges.college_id"), nullable=False
    )
    created_by_officer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("campus_placement_officers.officer_id"),
        nullable=False,
    )

    drive_name = Column(String(255), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)

    # NEW RELATIONSHIP
    target_batch_id = Column(
        UUID(as_uuid=True), ForeignKey("student_batches.batch_id"), nullable=False
    )

    min_cgpa = Column(Integer)
    max_backlogs = Column(Integer)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())

    college = relationship("College", back_populates="drives")

    officer = relationship("CampusPlacementOfficer")
    target_batch = relationship("StudentBatch")
    companies = relationship(
        "CampusDriveCompany", back_populates="drive", cascade="all, delete-orphan"
    )
    placements = relationship(
        "CampusPlacement", back_populates="drive", cascade="all, delete-orphan"
    )


class CampusDriveCompany(Base):
    __tablename__ = "campus_drive_companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    drive_id = Column(
        UUID(as_uuid=True), ForeignKey("campus_drives.drive_id"), nullable=False
    )
    company_id = Column(
        UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False
    )
    added_at = Column(DateTime, default=func.now())

    drive = relationship("CampusDrive", back_populates="companies")
    company = relationship("Company", back_populates="drives")
