from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    Boolean,
    Integer,
    ForeignKey,
    ARRAY,
    JSON,
    TIMESTAMP,
    Float,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database.db import Base
from datetime import datetime

# from uuid import uuid4
import uuid
from sqlalchemy.sql import func
from sqlalchemy import Enum as SQLEnum
from enum import Enum


class HackathonStatus(str, Enum):
    upcoming = "Upcoming"
    active = "Active"
    completed = "Completed"


class Hackathon(Base):
    __tablename__ = "hackathons"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # employer_id = Column(UUID(as_uuid=True), ForeignKey("employer_profiles.employer_id", ondelete="CASCADE"))
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE")
    )
    name = Column(String, nullable=False)
    description = Column(Text)
    start_date = Column(TIMESTAMP, nullable=False)
    end_date = Column(TIMESTAMP, nullable=False)
    registration_deadline = Column(TIMESTAMP, nullable=False)
    mode = Column(String, nullable=False)
    theme = Column(String)
    eligibility_criteria = Column(Text)
    min_team_size = Column(Integer, nullable=False)
    max_team_size = Column(Integer, nullable=False)
    submission_guidelines = Column(Text)
    rules = Column(ARRAY(String))
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    timeline = Column(JSON)
    status = Column(String, default="Upcoming")
    image = Column(String, nullable=True)
    featured = Column(Boolean, default=False)
    prizes = Column(ARRAY(String), nullable=True)
    sponsoredBy = Column(ARRAY(String), nullable=True)
    location = Column(String, nullable=False)

    problem_statements = relationship(
        "ProblemStatement", back_populates="hackathon", cascade="all, delete-orphan"
    )
    registrations = relationship(
        "HackathonRegistration",
        back_populates="hackathon",
        cascade="all, delete-orphan",
    )

    scorings = relationship(
        "Scoring", back_populates="hackathon", cascade="all, delete-orphan"
    )


class ProblemStatement(Base):
    __tablename__ = "problem_statements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hackathon_id = Column(
        UUID(as_uuid=True),
        ForeignKey("hackathons.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)

    hackathon = relationship("Hackathon", back_populates="problem_statements")
    scorings = relationship("Scoring", back_populates="problem_statement")


class HackathonRegistration(Base):
    __tablename__ = "hackathon_registrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(
        UUID(as_uuid=True),
        ForeignKey("team.team_id", ondelete="CASCADE"),
        nullable=False,
    )
    hackathon_id = Column(
        UUID(as_uuid=True),
        ForeignKey("hackathons.id", ondelete="CASCADE"),
        nullable=False,
    )
    agreed_to_eligibility = Column(Boolean, default=False)

    team = relationship("Team", back_populates="registrations")
    hackathon = relationship("Hackathon", back_populates="registrations")


class Team(Base):
    __tablename__ = "team"

    team_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_name = Column(String(100), unique=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    members = relationship(
        "TeamStudent", back_populates="team", cascade="all, delete-orphan"
    )
    registrations = relationship(
        "HackathonRegistration", back_populates="team", cascade="all, delete-orphan"
    )

    scorings = relationship(
        "Scoring", back_populates="team", cascade="all, delete-orphan"
    )


class TeamStudent(Base):
    __tablename__ = "team_student"

    team_id = Column(
        UUID(as_uuid=True),
        ForeignKey("team.team_id", ondelete="CASCADE"),
        primary_key=True,
        default=uuid.uuid4,
    )
    student_id = Column(
        UUID(as_uuid=True),
        ForeignKey("students.student_id", ondelete="CASCADE"),
        primary_key=True,
        default=uuid.uuid4,
    )

    team = relationship("Team", back_populates="members")


class SubmissionType(str, Enum):
    ZIP = "zip"
    GITHUB = "github"
    URL = "url"


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    submission_type = Column(
        SQLEnum(SubmissionType, name="submission_type"), nullable=False
    )

    # For zip files
    filename = Column(String, nullable=True)
    filepath = Column(String, nullable=True)

    # Common field for GitHub/URL/any value
    submission_value = Column(String, nullable=False)

    problem_statement_id = Column(
        UUID(as_uuid=True), ForeignKey("problem_statements.id"), nullable=False
    )
    hackathon_id = Column(
        UUID(as_uuid=True), ForeignKey("hackathons.id"), nullable=False
    )
    team_id = Column(UUID(as_uuid=True), ForeignKey("team.team_id"), nullable=False)

    submitted_at = Column(DateTime(timezone=True), server_default=func.now())

    scorings = relationship("Scoring", back_populates="submission")


class Scoring(Base):
    __tablename__ = "scorings"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    hackathon_id = Column(
        UUID(as_uuid=True), ForeignKey("hackathons.id"), nullable=False
    )
    problem_statement_id = Column(
        UUID(as_uuid=True), ForeignKey("problem_statements.id"), nullable=False
    )
    team_id = Column(UUID(as_uuid=True), ForeignKey("team.team_id"), nullable=False)
    submission_id = Column(
        UUID(as_uuid=True), ForeignKey("submissions.id"), nullable=False
    )

    score = Column(Float, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    hackathon = relationship("Hackathon", back_populates="scorings")
    problem_statement = relationship("ProblemStatement", back_populates="scorings")
    team = relationship("Team", back_populates="scorings")
    submission = relationship("Submission", back_populates="scorings")
