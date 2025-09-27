import uuid
from sqlalchemy import Column, String, Text, Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database.db import Base


class PersonalInfo(Base):
    __tablename__ = "personal_info"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id = Column(UUID(as_uuid=True), ForeignKey("resume_versions.version_id", ondelete="CASCADE"))
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.student_id", ondelete="CASCADE"))
    full_name = Column(String(255))
    email = Column(String(255))
    phone = Column(String(50))
    location = Column(String(255))
    bio = Column(Text)

    company_experiences = relationship("CompanyExperience", back_populates="user", cascade="all, delete-orphan")
    skills = relationship("Skill", back_populates="user", cascade="all, delete-orphan")
    certifications = relationship("Certification", back_populates="user", cascade="all, delete-orphan")
    social_profiles = relationship("SocialProfile", back_populates="user", cascade="all, delete-orphan")
    education = relationship("Education", back_populates="user", cascade="all, delete-orphan")
    languages = relationship("Language", back_populates="user", cascade="all, delete-orphan")
    projects = relationship("Projects", back_populates="user", cascade="all, delete-orphan")


class CompanyExperience(Base):
    __tablename__ = "company_experience"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("personal_info.id", ondelete="CASCADE"))
    company_name = Column(String(255))
    your_position = Column(String(255))
    dates = Column(String(255))
    company_website = Column(String(255))
    company_location = Column(String(255))
    company_description = Column(Text)
    company_logo = Column(String)

    user = relationship("PersonalInfo", back_populates="company_experiences")
    work_experiences = relationship("WorkExperience", back_populates="company", cascade="all, delete-orphan")


class WorkExperience(Base):
    __tablename__ = "work_experience"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("company_experience.id", ondelete="CASCADE"))
    position_title = Column(String(255))
    company_name = Column(String(255))
    duration = Column(String(100))
    description = Column(Text)

    company = relationship("CompanyExperience", back_populates="work_experiences")


class Skill(Base):
    __tablename__ = "skills"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("personal_info.id", ondelete="CASCADE"))
    skill_name = Column(Text)
    category = Column(String(100))

    user = relationship("PersonalInfo", back_populates="skills")


class Certification(Base):
    __tablename__ = "certifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("personal_info.id", ondelete="CASCADE"))
    certification_name = Column(String(255))
    issued_by = Column(String(255))
    issue_date = Column(Date)
    expiration_date = Column(Date)

    user = relationship("PersonalInfo", back_populates="certifications")


class SocialProfile(Base):
    __tablename__ = "social_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("personal_info.id", ondelete="CASCADE"))
    personal_website = Column(String(255))
    linkedin = Column(String(255))
    github = Column(String(255))
    twitter = Column(String(255))

    user = relationship("PersonalInfo", back_populates="social_profiles")


class Education(Base):
    __tablename__ = "education"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("personal_info.id", ondelete="CASCADE"))
    institution_name = Column(String(255))
    degree = Column(String(255))
    field_of_study = Column(String(255))
    start_date = Column(Date)
    end_date = Column(Date)
    grade = Column(String(50))
    description = Column(Text)

    user = relationship("PersonalInfo", back_populates="education")


class Language(Base):
    __tablename__ = "languages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("personal_info.id", ondelete="CASCADE"))
    language_name = Column(String(100))
    proficiency_level = Column(String(100))

    user = relationship("PersonalInfo", back_populates="languages")

class Projects(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("personal_info.id", ondelete="CASCADE"))
    title = Column(Text)
    dates = Column(Text)
    details = Column(Text)

    user = relationship("PersonalInfo", back_populates="projects")
