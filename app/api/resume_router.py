from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.db import get_db
from app.schemas.resume_schemas import (
    ResumeTypeEnum,
    ResumeVersionResponse,
)
from app.services.resume_screener_service import (
    resume_vectorstore_v2,
)
from app.services.resume_service import (
    create_resume_version_profile,
    delete_resume_and_files,
    get_resumes_by_user_id,
    get_all_resumes,
    download_file,
)

router = APIRouter(prefix="/api/resumes", tags=["Resumes"])


@router.post("/upload_resume")
async def upload_resume_profile(
    background_tasks: BackgroundTasks,
    resume_name: str = Form(...),
    user_id: UUID = Form(...),
    resume_type: ResumeTypeEnum = Form(...),
    source_resume_id: Optional[UUID] = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a resume for a user and extract structured data.

    Args:
        background_tasks (BackgroundTasks): FastAPI background task manager.
        resume_name (str): Name assigned to the resume.
        user_id (UUID): UUID of the user.
        resume_type (ResumeTypeEnum): Type/category of resume.
        template_id (Optional[UUID]): Resume template reference.
        source_resume_id (Optional[UUID]): Resume to clone from, if any.
        file (UploadFile): The uploaded resume file.
        db (AsyncSession): Asynchronous database session.

    Returns:
        dict: ATS score and AI feedback for the uploaded resume.
    """
    return await create_resume_version_profile(
        db=db,
        user_id=user_id,
        resume_type=resume_type,
        resume_name=resume_name,
        source_resume_id=source_resume_id,
        file=file,
        background_tasks=background_tasks,
    )


@router.get("/get_resume/{user_id}", response_model=list[ResumeVersionResponse])
async def fetch_resumes_by_user_v2(user_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Fetch all uploaded resumes for a specific user.

    Args:
        user_id (UUID): The UUID of the user.
        db (AsyncSession): Async database session.

    Returns:
        list[ResumeVersionResponse]: List of resume versions associated with the user.
    """
    return await get_resumes_by_user_id(user_id, db)


@router.get("/get_resumes")
async def fetch_all_resumes(db: AsyncSession = Depends(get_db)):
    """
    Fetch all resume versions for all students.

    Args:
        db (AsyncSession): Async database session.

    Returns:
        list[ResumeVersionResponse]: List of all resumes across all users.
    """
    results = await get_all_resumes(db)
    return [
        ResumeVersionResponse(**resume.__dict__, user_id=user_id)
        for resume, user_id in results
    ]


@router.post("/resume_vectorStore/{user_id}")
async def resume_vectorStore_db(user_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await resume_vectorstore_v2(user_id=user_id, db=db)
    return result


@router.get("/download")
async def download_file_api(
    version_id: UUID = Query(..., description="Resume Version ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    API endpoint to download a resume file by version ID.

    Args:
        version_id (UUID): Resume version to download.
        db (AsyncSession): Dependency-injected async DB session.

    Returns:
        StreamingResponse: Downloadable resume file.
    """
    return await download_file(version_id, db)


@router.delete("/delete_resumes/{user_id}")
async def delete_resumes(user_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Delete all resume versions and associated files for a user, and remove the user's resume vector from Qdrant.
    """
    return await delete_resume_and_files(user_id, db)
