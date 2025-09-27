from sqlalchemy.orm import Session
from app.services.articles_services import ArticleService
from app.database.db import get_db


def refresh_articles():
    """
    Cron job function to refresh articles.
    This should be scheduled to run every 7 days.
    """
    db: Session = next(get_db())
    try:
        article_service = ArticleService(db)
        article_service.fetch_and_store_articles()
        print("Successfully refreshed articles")
    except Exception as e:
        print(f"Error refreshing articles: {str(e)}")
    finally:
        db.close()
