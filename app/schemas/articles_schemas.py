from pydantic import BaseModel, HttpUrl
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from app.database.models.articles_models import TopicEnum


class ArticleBase(BaseModel):
    title: str
    excerpt: Optional[str]
    url: HttpUrl
    authors: Optional[List[str]]  # Will be converted from JSON string
    published_date: datetime
    topic: TopicEnum


class ArticleCreate(ArticleBase):
    pass


class ArticleRead(ArticleBase):
    article_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class SaveArticleRequest(BaseModel):
    user_id: UUID
    article_id: UUID
