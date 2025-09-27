import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from app.database.db import get_db
from app.database.models.bookmark_models import Bookmark
from app.database.models.job_postings_models import JobPosting
from app.database.models.students_models import Student
from app.schemas.job_postings_schema import BookmarkCreate, BookmarkRead
from app.utils.logger_config import logger
from sqlalchemy.orm import selectinload

router = APIRouter(
    prefix="/api/bookmarks",
    tags=["Bookmarks"],
    responses={
        404: {"description": "Not found"},
        400: {"description": "Invalid input"},
        409: {"description": "Bookmark already exists"},
        500: {"description": "Internal server error"},
    },
)


@router.post(
    "",
    response_model=BookmarkRead,
    status_code=status.HTTP_201_CREATED,
    summary="Save a Job Bookmark",
    description="Bookmarks a job posting for a student using their user ID.",
)
async def create_bookmark(bookmark: BookmarkCreate, db: AsyncSession = Depends(get_db)):
    """
    Save a job posting as a bookmark for a student.

    - **job_id**: UUID of the job posting to bookmark.
    - **user_id**: UUID of the user (mapped to student via students table).
    """
    try:
        # Resolve student from user_id
        student = (
            await db.execute(
                select(Student).filter(Student.user_id == bookmark.user_id)
            )
        ).scalar_one_or_none()
        if not student:
            logger.warning(f"No student found for user_id: {bookmark.user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No student found for user ID {bookmark.user_id}",
            )

        # Validate the job is active
        job = (
            await db.execute(
                select(JobPosting).filter(
                    JobPosting.job_id == bookmark.job_id,
                    JobPosting.is_active,
                )
            )
        ).scalar_one_or_none()
        if not job:
            logger.warning(f"Active job not found: {bookmark.job_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Active job with ID {bookmark.job_id} not found",
            )

        # Check for existing bookmark
        existing = (
            await db.execute(
                select(Bookmark).filter(
                    Bookmark.student_id == student.student_id,
                    Bookmark.job_id == bookmark.job_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            logger.warning(
                f"Bookmark already exists for student_id={student.student_id}, job_id={bookmark.job_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bookmark already exists for this job and student",
            )

        # Create bookmark
        new_bookmark = Bookmark(job_id=bookmark.job_id, student_id=student.student_id)
        db.add(new_bookmark)
        await db.commit()
        await db.refresh(new_bookmark)

        logger.info(f"Created bookmark: {new_bookmark.bookmark_id}")
        return BookmarkRead(
            bookmark_id=new_bookmark.bookmark_id,
            job_id=new_bookmark.job_id,
            student_id=new_bookmark.student_id,
            job_title=job.title,
            company_name=job.company_name,
            job_location=job.location,
            job_type=job.job_type,
            posted_at=job.posted_at,
        )

    except IntegrityError as e:
        await db.rollback()
        logger.error(f"Integrity error while creating bookmark: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid job_id or student_id",
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error creating bookmark: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error creating bookmark",
        )


@router.get(
    "/student/{user_id}",
    response_model=List[BookmarkRead],
    summary="Get Bookmarks for a Student",
    description="Retrieves all bookmarked jobs for a student using their user ID.",
)
async def get_student_bookmarks(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Get all job bookmarks for a specific student.

    - **user_id**: UUID of the user (mapped to student_id).
    """
    try:
        student = (
            await db.execute(select(Student).filter(Student.user_id == user_id))
        ).scalar_one_or_none()
        if not student:
            logger.warning(f"No student found for user_id: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No student found for user ID {user_id}",
            )

        results = await db.execute(
            select(Bookmark)
            .options(selectinload(Bookmark.job))  # Eager load job relation
            .join(JobPosting)
            .filter(
                Bookmark.student_id == student.student_id,
                JobPosting.is_active,
            )
        )
        bookmarks = results.scalars().all()

        response = [
            BookmarkRead(
                bookmark_id=b.bookmark_id,
                job_id=b.job_id,
                student_id=b.student_id,
                job_title=b.job.title,
                company_name=b.job.company_name,
                job_location=b.job.location,
                job_type=b.job.job_type,
                posted_at=b.job.posted_at,
            )
            for b in bookmarks
        ]

        logger.info(
            f"Retrieved {len(response)} bookmarks for student_id={student.student_id}"
        )
        return response

    except Exception as e:
        logger.error(
            f"Unexpected error retrieving bookmarks for user_id={user_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error retrieving bookmarks",
        )


@router.delete(
    "/{bookmark_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a Bookmark",
    description="Deletes a specific job bookmark using its bookmark ID.",
)
async def delete_bookmark(bookmark_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Delete a job bookmark using its unique bookmark ID.

    - **bookmark_id**: UUID of the bookmark.
    """
    try:
        bookmark = (
            await db.execute(
                select(Bookmark).filter(Bookmark.bookmark_id == bookmark_id)
            )
        ).scalar_one_or_none()
        if not bookmark:
            logger.warning(f"Bookmark not found: {bookmark_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Bookmark with ID {bookmark_id} not found",
            )

        await db.delete(bookmark)
        await db.commit()
        logger.info(f"Deleted bookmark: {bookmark_id}")
        return {"message": "Bookmark deleted successfully"}

    except Exception as e:
        await db.rollback()
        logger.error(
            f"Unexpected error deleting bookmark {bookmark_id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error deleting bookmark",
        )
