import json
import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, delete
from sqlalchemy.exc import SQLAlchemyError

from app.database.models.articles_models import Article, SavedArticle, TopicEnum
from app.services.news_client_service import NewsClientService
from app.utils.settings import settings
from app.schemas.articles_schemas import ArticleRead


class ArticleService:
    """
    Service class for managing news articles and user-saved articles.

    This service handles fetching articles from an external news API,
    storing them in the database, retrieving articles, and managing user-specific saved articles.
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize the ArticleService.

        Args:
            db (AsyncSession): SQLAlchemy asynchronous session instance for DB operations.
        """
        self.db = db
        self.news_client = NewsClientService(api_key=settings.RAPID_API_KEY_ARTICLES)

    async def fetch_and_store_articles(self) -> None:
        """
        Fetch and store articles from the news API for each topic.

        - Loops through all `TopicEnum` values.
        - Fetches articles using the external API.
        - Parses and saves the results into the database.
        - Commits changes at the end of all insertions.

        Exceptions during API fetch or DB insert for a topic are logged and skipped.
        """
        for topic in TopicEnum:
            try:
                results = await self.news_client.search_articles(
                    query=topic.value,
                    language="en",
                    limit=2,
                )

                articles = results.get("data", [])

                for article_data in articles:
                    published_date = self.news_client.format_article_date(
                        article_data["date"]
                    )
                    published_date = published_date.replace(tzinfo=None)

                    article = Article(
                        article_id=uuid.uuid4(),
                        title=article_data["title"],
                        excerpt=article_data.get("excerpt"),
                        url=article_data["url"],
                        authors=json.dumps(article_data.get("authors", [])),
                        published_date=published_date,
                        topic=topic,
                    )

                    self.db.add(article)

            except Exception as e:
                print(f"Error fetching articles for topic {topic.value}: {str(e)}")
                continue

        await self.db.commit()

    async def get_articles(
        self, topic: Optional[TopicEnum] = None
    ) -> List[ArticleRead]:
        """
        Retrieve articles from the database.

        Args:
            topic (Optional[TopicEnum]): Optional filter to get articles by topic.

        Returns:
            List[ArticleRead]: List of articles with authors parsed from JSON.
        """
        stmt = select(Article).order_by(desc(Article.published_date))
        if topic:
            stmt = stmt.filter(Article.topic == topic)

        result = await self.db.execute(stmt)
        articles = result.scalars().all()
        return [self._to_article_read(article) for article in articles]

    async def save_article_for_user(
        self, user_id: uuid.UUID, article_id: uuid.UUID
    ) -> bool:
        """
        Save an article to a user's saved list.

        Args:
            user_id (uuid.UUID): The ID of the user.
            article_id (uuid.UUID): The ID of the article to be saved.

        Returns:
            bool: True if saved successfully, False otherwise.
        """
        try:
            saved_article = SavedArticle(user_id=user_id, article_id=article_id)
            self.db.add(saved_article)
            await self.db.commit()
            return True
        except SQLAlchemyError as e:
            await self.db.rollback()
            print(f"Error saving article: {str(e)}")
            return False

    async def unsave_article_for_user(
        self, user_id: uuid.UUID, article_id: uuid.UUID
    ) -> bool:
        """
        Remove a saved article from a user's list.

        Args:
            user_id (uuid.UUID): The ID of the user.
            article_id (uuid.UUID): The ID of the article to be removed.

        Returns:
            bool: True if removed successfully, False otherwise.
        """
        try:
            stmt = delete(SavedArticle).where(
                SavedArticle.user_id == user_id,
                SavedArticle.article_id == article_id,
            )
            await self.db.execute(stmt)
            await self.db.commit()
            return True
        except SQLAlchemyError as e:
            await self.db.rollback()
            print(f"Error unsaving article: {str(e)}")
            return False

    async def get_saved_articles_for_user(
        self, user_id: uuid.UUID
    ) -> List[ArticleRead]:
        """
        Retrieve all articles saved by a specific user.

        Args:
            user_id (uuid.UUID): The ID of the user.

        Returns:
            List[ArticleRead]: List of saved articles with parsed author data.
        """
        stmt = (
            select(Article)
            .join(SavedArticle)
            .filter(SavedArticle.user_id == user_id)
            .order_by(desc(Article.published_date))
        )
        result = await self.db.execute(stmt)
        articles = result.scalars().all()
        return [self._to_article_read(article) for article in articles]

    async def get_all_articles(self) -> List[ArticleRead]:
        """
        Retrieve all articles from the database regardless of topic.

        Returns:
            List[ArticleRead]: List of all articles ordered by published date.
        """
        stmt = select(Article).order_by(desc(Article.published_date))
        result = await self.db.execute(stmt)
        articles = result.scalars().all()
        return [self._to_article_read(article) for article in articles]

    def _to_article_read(self, article: Article) -> ArticleRead:
        """
        Convert a database `Article` model instance to a `ArticleRead` schema.

        Args:
            article (Article): The SQLAlchemy Article model instance.

        Returns:
            ArticleRead: Pydantic-compatible version of the article with parsed authors.
        """
        try:
            authors = json.loads(article.authors) if article.authors else []
            if not isinstance(authors, list):
                authors = [str(authors)]
        except (json.JSONDecodeError, TypeError):
            authors = []

        return ArticleRead(
            article_id=article.article_id,
            title=article.title,
            excerpt=article.excerpt,
            url=article.url,
            authors=authors,
            published_date=article.published_date,
            topic=article.topic,
            created_at=article.created_at,
        )
