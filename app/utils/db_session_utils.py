from contextlib import asynccontextmanager
from app.database.db import async_session_maker


@asynccontextmanager
async def get_new_session():
    async with async_session_maker() as db:
        yield db


async def run_with_new_session(func, *args, **kwargs):
    async with async_session_maker() as db:
        return await func(*args, db=db, **kwargs)
