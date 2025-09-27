from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models.hackathon_models import Hackathon
from app.utils.logger_config import logger
import asyncio
from app.database.db import async_session_maker


async def delete_old_hackathons(db: AsyncSession):
    """
    Asynchronously deletes hackathons whose end_date has passed beyond a 1-day threshold.

    Args:
        db (AsyncSession): SQLAlchemy async session object.
    """
    logger.info("Running weekly hackathon cleanup job...")

    try:
        threshold_date = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(
            days=1
        )

        # Select expired hackathons
        result = await db.execute(
            select(Hackathon).filter(Hackathon.end_date <= threshold_date)
        )
        expired_hackathons = result.scalars().all()

        for hackathon in expired_hackathons:
            logger.info(
                f"Deleting expired hackathon: {hackathon.name} (ID: {hackathon.id})"
            )
            await db.delete(hackathon)

        await db.commit()
        logger.info(f"Deleted {len(expired_hackathons)} expired hackathons.")

    except Exception as e:
        logger.error(f"Error while cleaning up hackathons: {e}")
        await db.rollback()


def run_delete_old_hackathons():
    """
    APScheduler-compatible sync wrapper that initializes
    the async DB session and runs the cleanup coroutine.
    """

    async def _inner():
        async with async_session_maker() as db:
            await delete_old_hackathons(db)

    asyncio.run(_inner())
