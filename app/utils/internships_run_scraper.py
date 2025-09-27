import asyncio
import random
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.db import get_db, async_session_maker
from app.services.internships_recommendation_service import (
    upload_internships_to_qdrant_v2,
)
from app.services.internships_service import InternshipScraper, InternshipRepository
from app.services.resume_screener_service import batch_resume_internship_matching
from app.utils.logger_config import logger
from app.utils.settings import settings

# TODO: Need to update run_scrapper function so that it is asynchronous with a delay.


async def run_scraper():
    scraper = InternshipScraper()
    try:
        # Define one-to-one mappings
        job_targets = [
            ("India", "Software Developer", "Technology"),
            ("India", "ML Engineer", "Technology"),
            ("India", "Data Analyst", "Technology"),
            ("India", "UI/UX Designer", "Technology"),
            ("India", "Human Resources", "Human Resources"),
            ("India", "Marketing", "Marketing"),
            ("Singapore", "Software Developer", "Technology"),
            ("Singapore", "ML Engineer", "Technology"),
            ("Singapore", "Data Analyst", "Technology"),
            ("Singapore", "UI/UX Designer", "Technology"),
            ("Singapore", "Human Resources", "Human Resources"),
            ("Singapore", "Marketing", "Marketing"),
            ("United States", "Software Developer", "Technology"),
            ("United States", "ML Engineer", "Technology"),
            ("United States", "Data Analyst", "Technology"),
            ("United States", "UI/UX Designer", "Technology"),
            ("United States", "Human Resources", "Human Resources"),
            ("United States", "Marketing", "Marketing"),
            ("United Arab Emirates", "Software Developer", "Technology"),
            ("United Arab Emirates", "ML Engineer", "Technology"),
            ("United Arab Emirates", "Data Analyst", "Technology"),
            ("United Arab Emirates", "UI/UX Designer", "Technology"),
            ("United Arab Emirates", "Human Resources", "Human Resources"),
            ("United Arab Emirates", "Marketing", "Marketing"),
            ("United Kingdom", "Software Developer", "Technology"),
            ("United Kingdom", "ML Engineer", "Technology"),
            ("United Kingdom", "Data Analyst", "Technology"),
            ("United Kingdom", "UI/UX Designer", "Technology"),
            ("United Kingdom", "Human Resources", "Human Resources"),
            ("United Kingdom", "Marketing", "Marketing"),
            # Add more pairs as needed
        ]
        random.shuffle(job_targets)

        DEFAULT_QUERY_PARAMS = {
            "location_filter": "",
            "description_type": "text",
            "include_ai": "true",
            "description_filter": "",
        }
        semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_REQUESTS_RAPID_API_INTERNSHIPS)
        async with async_session_maker() as db:
            db_handler = InternshipRepository(db)

            async def fetch_and_store(country: str, role: str, category: str):
                async with semaphore:
                    logger.info(f"Fetching for: {country}, role: {role}")
                    params = DEFAULT_QUERY_PARAMS.copy()
                    params["location_filter"] = country
                    params["description_filter"] = role
                    try:
                        listings = await scraper.fetch_job_listings(params, role, category)
                        await db_handler.insert_bulk(listings)
                    except Exception as e:
                        logger.error(
                            f"Error while fetching job listings for {country}, {role} — {e}"
                        )

            await asyncio.gather(*[
                fetch_and_store(country, role, category)
                for country, role, category in job_targets
            ])
    except Exception as e:
        logger.error(f"Error while fetching internships : {e}")
        raise
    finally:
        if scraper:
            await scraper.close()


async def combine_fetching_recommendations(db: AsyncSession):
    await run_scraper()
    await upload_internships_to_qdrant_v2(db=db)
    await batch_resume_internship_matching(db=db)


async def internships_scraper():
    async with async_session_maker() as db:
        try:
            await combine_fetching_recommendations(db)
        except Exception as e:
            logger.error(f"Internship scraper failed: {e}")


async def deactivate_expired_internships_job():
    """
    Background job to deactivate expired internships.
    Meant to be scheduled with APScheduler.
    """
    async with async_session_maker() as db:
        repository = InternshipRepository(db)
        try:
            message = await repository.deactivate_expired_internships_service()
            logger.info(f"Cron: {message}")
        except Exception as e:
            logger.error(f"Cron job failed to deactivate internships: {e}")
