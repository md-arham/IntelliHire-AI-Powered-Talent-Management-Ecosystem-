from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID
from fastapi import Depends, HTTPException, APIRouter
from app.database.db import get_db
from app.database.models.articles_models import TopicEnum
from app.services.articles_services import ArticleService
from app.schemas.articles_schemas import ArticleRead, SaveArticleRequest
from app.utils.logger_config import logger

router = APIRouter(prefix="/api/articles", tags=["Articles"])


@router.get("/", response_model=List[ArticleRead])
async def get_articles(
    topic: Optional[TopicEnum] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Get all news articles, optionally filtered by topic.

    - **topic**: Optional query parameter to filter articles by a specific topic.
    - Returns a list of articles sorted by most recent publication date.

    Possible topics:
    - Technology
    - AI
    - Science
    - Business
    - Education
    """
    try:
        article_service = ArticleService(db)
        return await article_service.get_articles(topic)
    except Exception as e:
        logger.error(f"Error fetching articles: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch articles")


@router.post("/save")
async def save_article(
    payload: SaveArticleRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Save a specific article to a user's saved list.

    - **payload.user_id**: UUID of the user.
    - **payload.article_id**: UUID of the article to be saved.
    - Returns a success message if saved, else raises error.
    """
    try:
        article_service = ArticleService(db)
        success = await article_service.save_article_for_user(
            payload.user_id, payload.article_id
        )
        if not success:
            raise HTTPException(status_code=400, detail="Failed to save article")
        return {"message": "Article saved successfully"}
    except Exception as e:
        logger.error(f"Error saving article: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/unsave/{user_id}/{article_id}")
async def unsave_article(
    user_id: UUID,
    article_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Unsave (remove) an article from a user's saved list.

    - **user_id**: UUID of the user.
    - **article_id**: UUID of the article to be removed.
    - Returns a success message if removed, else raises error.
    """
    try:
        article_service = ArticleService(db)
        success = await article_service.unsave_article_for_user(user_id, article_id)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to unsave article")
        return {"message": "Article unsaved successfully"}
    except Exception as e:
        logger.error(f"Error unsaving article: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/saved/{user_id}", response_model=List[ArticleRead])
async def list_saved_articles(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get all articles saved by a specific user.

    - **user_id**: UUID of the user whose saved articles should be retrieved.
    - Returns a list of saved articles in reverse chronological order.
    """
    try:
        article_service = ArticleService(db)
        return await article_service.get_saved_articles_for_user(user_id)
    except Exception as e:
        logger.error(f"Error fetching saved articles for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch saved articles")


@router.post("/refresh")
async def refresh_now(db: AsyncSession = Depends(get_db)):
    """
    Manually trigger a refresh to fetch new articles from the external news API.

    - Loops through all available topics.
    - Fetches latest articles and stores them in the database.
    - Returns a success message when complete.
    """
    try:
        article_service = ArticleService(db)
        await article_service.fetch_and_store_articles()
        return {"message": "Articles refreshed successfully"}
    except Exception as e:
        logger.error(f"Error refreshing articles: {e}")
        raise HTTPException(status_code=500, detail="Failed to refresh articles")
