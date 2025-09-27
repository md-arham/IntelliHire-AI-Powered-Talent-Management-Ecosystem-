from sqlalchemy.orm import Session
from app.services.articles_services import ArticleService
from app.database.db import get_db


def populate_database():
    """
    Manually populate the database with articles for all topics.
    This can be run whenever you want to refresh the articles immediately.
    """
    print("Starting database population...")
    db: Session = next(get_db())

    try:
        article_service = ArticleService(db)
        article_service.fetch_and_store_articles()
        print("Successfully populated database with articles!")

    except Exception as e:
        print(f"Error populating database: {str(e)}")

    finally:
        db.close()


if __name__ == "__main__":
    populate_database()
