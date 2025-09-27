from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import create_engine
from typing import Optional
from app.database.models.users_models import User  # Assuming the model is defined in models.py
from fastapi import HTTPException, status
from app.utils.logger_config import logger
from sqlalchemy import select

async def get_roles(db: AsyncSession, email: str) -> Optional[str]:
    result = await db.execute(select(User).filter(User.email == email))
    user = result.scalars().first()
    if not user:
        logger.error(f"User with email {email} not found.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with email {email} not found."
        )
    logger.info(f"Type of get_role function return type: {type(user.role.value)}")
    return user.role.value