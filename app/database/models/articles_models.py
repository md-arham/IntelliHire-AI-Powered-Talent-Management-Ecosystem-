from sqlalchemy import Column, String, Text, TIMESTAMP, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.db import Base
import enum
import uuid


class TopicEnum(enum.Enum):
    TECHNOLOGY = "Technology"
    AI = "AI"
    SCIENCE = "Science"
    BUSINESS = "Business"
    EDUCATION = "Education"


class Article(Base):
    __tablename__ = "articles"

    article_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    excerpt = Column(Text, nullable=True)
    url = Column(String(500), nullable=False)
    authors = Column(Text, nullable=True)  # Stored as JSON string
    published_date = Column(TIMESTAMP, nullable=False)
    topic = Column(Enum(TopicEnum), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())

    # Relationship with users through saved_articles
    saved_by_users = relationship("User", secondary="saved_articles")


class SavedArticle(Base):
    __tablename__ = "saved_articles"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), primary_key=True)
    article_id = Column(
        UUID(as_uuid=True), ForeignKey("articles.article_id"), primary_key=True
    )
    saved_at = Column(TIMESTAMP, server_default=func.now())
