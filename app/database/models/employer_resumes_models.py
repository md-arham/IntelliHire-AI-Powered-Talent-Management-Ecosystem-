import uuid
from sqlalchemy import (
    Column, PrimaryKeyConstraint, String, Text, ForeignKey, Boolean, TIMESTAMP, func, Float,Date
)
from sqlalchemy.dialects.postgresql import UUID, BYTEA
from sqlalchemy.orm import relationship
from app.database.db import Base  # Assuming your declarative base is imported from here

class EmployerResume(Base):
    __tablename__ = "employer_resumes"

    resume_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employer_profiles.employer_id", ondelete="CASCADE"),
        nullable=False,
    )
    filebytes = Column(BYTEA)
    file_path = Column(Text)
    created_at = Column(TIMESTAMP, server_default=func.now())
    is_active = Column(Boolean, default=True)

    # Relationships
    employer_profile = relationship("EmployerProfile", back_populates="employer_resumes")
    personal_info = relationship("EmployerResumePersonalInfo", back_populates="resume", uselist=False, cascade="all, delete-orphan")
    matchings = relationship("EmployerResumeMatching",back_populates="resume",cascade="all, delete-orphan")

class EmployerResumeMatching(Base):
    __tablename__ = "employer_resume_matching"
    __table_args__ = (
        PrimaryKeyConstraint('job_id', 'resume_id'),
    )

    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("job_postings.job_id", ondelete="CASCADE"),
        nullable=False,
    )
    resume_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employer_resumes.resume_id", ondelete = "CASCADE"),
        nullable=False
    )
    matching_score = Column(Float)
    matching_reason = Column(Text)
    selection_status = Column(Boolean, default=False)
    

    resume = relationship("EmployerResume", back_populates="matchings")
    job_posting = relationship("JobPosting", back_populates="employer_resume_matchings")


class EmployerResumePersonalInfo(Base):
    __tablename__ = "employer_resume_personalinfo"

    candidate_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resume_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employer_resumes.resume_id", ondelete="CASCADE"),
        nullable=False,
        unique=True
    )
    candidate_name = Column(String(255))
    email = Column(String(255))
    phone = Column(String(50))
    location = Column(String(255))
    bio = Column(Text)
    language = Column(String(100))

    # Relationship
    resume = relationship("EmployerResume", back_populates="personal_info")
    skills = relationship("EmployerResumeSkill", back_populates="personal_info", cascade="all, delete-orphan")
    projects = relationship("EmployerResumeProject", back_populates="personal_info", cascade="all, delete-orphan")
    education = relationship("EmployerResumeEducation", back_populates="personal_info", cascade="all, delete-orphan")
    work_experiences = relationship("EmployerResumeWorkExperience", back_populates="personal_info", cascade="all, delete-orphan")
    certifications = relationship("EmployerResumeCertification", back_populates="personal_info", cascade="all, delete-orphan")


class EmployerResumeSkill(Base):
    __tablename__ = "employer_resume_skills"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("employer_resume_personalinfo.candidate_id", ondelete="CASCADE"), nullable=False)
    skill_name = Column(String(100), nullable=False)
    category = Column(String(100))

    personal_info = relationship("EmployerResumePersonalInfo", back_populates="skills")


class EmployerResumeProject(Base):
    __tablename__ = "employer_resume_projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("employer_resume_personalinfo.candidate_id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    dates = Column(String(100))  # You may want to split into start_date, end_date if you need date filtering
    details = Column(Text)

    personal_info = relationship("EmployerResumePersonalInfo", back_populates="projects")


class EmployerResumeEducation(Base):
    __tablename__ = "employer_resume_education"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("employer_resume_personalinfo.candidate_id", ondelete="CASCADE"), nullable=False)
    institution_name = Column(String(255), nullable=False)
    degree = Column(String(100))
    field_of_study = Column(String(100))
    start_date = Column(Date)
    end_date = Column(Date)
    grade = Column(String(50))
    description = Column(Text)

    personal_info = relationship("EmployerResumePersonalInfo", back_populates="education")


class EmployerResumeWorkExperience(Base):
    __tablename__ = "employer_resume_workexperience"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("employer_resume_personalinfo.candidate_id", ondelete="CASCADE"), nullable=False)
    company_name = Column(String(255), nullable=False)
    position_title = Column(String(100))
    duration = Column(String(100))  # You may want to split into start_date, end_date for more control
    description = Column(Text)

    personal_info = relationship("EmployerResumePersonalInfo", back_populates="work_experiences")
    

class EmployerResumeCertification(Base):
    __tablename__ = "employer_resume_certifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("employer_resume_personalinfo.candidate_id", ondelete="CASCADE"), nullable=False)
    certification_name = Column(String(255), nullable=False)
    issued_by = Column(String(255))
    issue_date = Column(Date)
    expiration_date = Column(Date)

    personal_info = relationship("EmployerResumePersonalInfo", back_populates="certifications")