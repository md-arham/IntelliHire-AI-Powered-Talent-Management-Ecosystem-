import uuid
from sqlalchemy import Column, String, UUID, ForeignKey, JSON, Enum, Float, TIMESTAMP
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.db import Base
from app.database.models.enums_models import ResultEnum

class Question(Base):
    __tablename__ = 'questions'
    
    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    question_text = Column(String, nullable=False)
    topic = Column(String, nullable=False)
    proficiency = Column(String, nullable=False)
    
    answer = relationship("Answer", back_populates="question", uselist=False, cascade="all, delete-orphan")
    
    responses = relationship(
        "MockInterviewResponse",
        back_populates="question",
        cascade="all, delete-orphan"
    )

class Answer(Base):
    __tablename__ = 'answers'
    
    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    question_id = Column(UUID, ForeignKey('questions.id'), nullable=False, unique=True)
    choices = Column(JSON, nullable=False)  # JSON field to store {id: answer_text}
    correct_answer_id = Column(String, nullable=False)
    
    question = relationship("Question", back_populates="answer")

class MockInterviewSession(Base):
    __tablename__ = 'mock_interview_session'
    __table_args__ = {'extend_existing': True}

    session_id = Column(UUID, primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID, ForeignKey('students.student_id', ondelete='CASCADE'), nullable=False)
    score = Column(Float, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    
    student = relationship("Student", back_populates="mock_interview_sessions")
    responses = relationship("MockInterviewResponse", back_populates="session", cascade="all, delete-orphan")
    
class MockInterviewResponse(Base):
    __tablename__ = 'mock_interview_responses'
    __table_args__ = {'extend_existing': True}

    response_id = Column(UUID, primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID, ForeignKey('mock_interview_session.session_id', ondelete='CASCADE'), nullable=False)
    question_id = Column(UUID, ForeignKey('questions.id', ondelete='CASCADE'), nullable=False)
    user_answer_id = Column(String, nullable=True)
    result = Column(Enum(ResultEnum, name='result_enum', create_type=True), nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    
    session = relationship("MockInterviewSession", back_populates="responses")
    question = relationship("Question", back_populates="responses")
