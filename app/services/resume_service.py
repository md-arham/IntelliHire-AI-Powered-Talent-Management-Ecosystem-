import os
from io import BytesIO
import aiofiles
from uuid import UUID, uuid4
import asyncio
from fastapi import BackgroundTasks, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import ResumeVersion, Student, PersonalInfo
from app.utils.db_session_utils import run_with_new_session
from app.services.resume_screener_service import (
    recommend_jobs_combined,
    resume_vectorstore_v2,
)

from app.utils.logger_config import logger
from app.utils.resume_extractor import (
    store_personal_info_V2,
    store_skills_from_json_V2,
    store_projects_from_json_V2,
    store_education_from_json_V2,
    store_languages_from_json_V2,
    store_certifications_from_json_V2,
    store_social_profiles_from_json_V2,
    store_company_and_work_experience_V2,
    extract_resume_data_v2,
)

from app.utils.settings import settings, qdrant_client


async def save_resume_to_disk_async(
    file: UploadFile, student_id: UUID, file_bytes: bytes = None
) -> str:
    """
    Asynchronously save resume file to disk with improved error handling and validation.

    Args:
        file: UploadFile object
        student_id: UUID of the student
        file_bytes: Pre-read file bytes (optional, will read from file if not provided)

    Returns:
        str: Normalized file path
    """
    if not file.filename:
        raise ValueError("File must have a filename")

    # Clean and validate filename
    clean_filename = os.path.basename(file.filename)
    if not clean_filename:
        raise ValueError("Invalid filename")

    # Extract and validate extension
    filename_parts = clean_filename.split(".")
    if len(filename_parts) < 2:
        raise ValueError("File must have an extension")

    extension = filename_parts[-1].lower()

    # Optional: Validate allowed extensions
    allowed_extensions = {"pdf", "doc", "docx"}
    if extension not in allowed_extensions:
        raise ValueError(
            f"File extension '{extension}' not allowed. Allowed: {', '.join(allowed_extensions)}"
        )

    # Generate unique filename
    unique_filename = f"{uuid4()}.{extension}"

    # Create student directory
    student_dir = os.path.join(settings.UPLOAD_RESUME_FOLDER, str(student_id))
    os.makedirs(student_dir, exist_ok=True)

    file_path = os.path.join(student_dir, unique_filename)

    try:
        # Use file_bytes if provided, otherwise read from file
        if file_bytes is None:
            await file.seek(0)
            file_bytes = await file.read()

        # Write file asynchronously
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_bytes)

        # Normalize path separators for cross-platform compatibility
        return file_path.replace("\\", "/")

    except Exception as e:
        # Clean up partial file if write failed
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass  # Ignore cleanup errors
        raise Exception(f"Failed to save resume file: {str(e)}")


async def create_resume_version_profile(
    db: AsyncSession,
    user_id: UUID,
    resume_type: str,
    resume_name: str,
    source_resume_id: UUID = None,
    file: UploadFile = None,
    background_tasks: BackgroundTasks = None,
    force_update_personal_info: bool = False,
):
    """
    Handles the full flow of uploading and processing a resume.

    Args:
        db (AsyncSession): SQLAlchemy async DB session.
        user_id (UUID): User ID.
        resume_type (str): Type/category of the resume.
        resume_name (str): Display name of the resume.
        file (UploadFile): The resume file uploaded.
        background_tasks (BackgroundTasks, optional): Background task manager.
        force_update_personal_info (bool): Whether to overwrite existing info.

    Returns:
        dict: Contains ATS score, AI feedback, and warnings if any.

    Raises:
        HTTPException: On validation or internal failure.
    """
    try:
        result = await db.execute(select(Student).filter(Student.user_id == user_id))
        student = result.scalars().first()
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")
    except Exception as e:
        logger.exception("Failed to retrieve student")
        raise HTTPException(status_code=500, detail="Failed to retrieve student") from e

    try:
        count_result = await db.execute(
            select(func.count(ResumeVersion.version_id)).filter(
                ResumeVersion.student_id == student.student_id
            )
        )
        if count_result.scalar() >= 5:
            raise HTTPException(
                status_code=400,
                detail="Resume upload limit reached. Delete a resume to upload a new one.",
            )
    except Exception as e:
        logger.exception("Failed to check resume upload limit")
        raise HTTPException(status_code=500, detail="Resume limit check failed") from e

    try:
        await file.seek(0)
        file_bytes = await file.read()
        file_path = await save_resume_to_disk_async(
            file, student.student_id, file_bytes
        )
    except Exception as e:
        logger.exception("Failed to save resume file")
        raise HTTPException(status_code=500, detail="Failed to save resume file") from e

    ats_score = 0
    ai_feedback = ""

    try:
        version_id = uuid4()
        resume = ResumeVersion(
            version_id=version_id,
            student_id=student.student_id,
            resume_type=resume_type,
            resume_name=resume_name,
            source_resume_id=source_resume_id,
            file=file_bytes,
            file_path=file_path,
        )
        db.add(resume)
        await db.flush()

        try:
            resume_data = await extract_resume_data_v2(
                BytesIO(file_bytes), file.filename
            )
        except Exception as e:
            logger.exception("Failed to extract data from resume")
            raise HTTPException(status_code=500, detail="Resume parsing failed") from e

        logger.info(f"Extracted Data: {resume_data}")
        resume_data["version_id"] = version_id
        resume_data["student_id"] = student.student_id

        personal_info_id = None
        try:
            result = await db.execute(
                select(PersonalInfo).filter(
                    PersonalInfo.student_id == student.student_id
                )
            )
            existing_info = result.scalar_one_or_none()
        except Exception as e:
            logger.exception("Failed to fetch existing personal info")
            raise HTTPException(status_code=500, detail="Database query failed") from e

        if not existing_info or force_update_personal_info:
            try:
                personal_info_id = await store_personal_info_V2(resume_data, db)
                if not personal_info_id:
                    logger.info("Personal Info creation failed")
                    raise HTTPException(
                        status_code=500, detail="Personal info processing failed"
                    )
            except Exception as e:
                logger.exception("Failed to create/update personal info")
                raise HTTPException(
                    status_code=500, detail="Personal info update error"
                ) from e

            try:
                ats_score_task = asyncio.create_task(calculate_ats_score(resume_data))

                await asyncio.gather(
                    run_with_new_session(
                        store_company_and_work_experience_V2,
                        resume_data,
                        personal_info_id,
                    ),
                    run_with_new_session(
                        store_skills_from_json_V2, resume_data, personal_info_id
                    ),
                    run_with_new_session(
                        store_certifications_from_json_V2, resume_data, personal_info_id
                    ),
                    run_with_new_session(
                        store_social_profiles_from_json_V2,
                        resume_data,
                        personal_info_id,
                    ),
                    run_with_new_session(
                        store_education_from_json_V2, resume_data, personal_info_id
                    ),
                    run_with_new_session(
                        store_languages_from_json_V2, resume_data, personal_info_id
                    ),
                    run_with_new_session(
                        store_projects_from_json_V2, resume_data, personal_info_id
                    ),
                )

                ats_score = await ats_score_task
                ai_feedback = resume_data.get("resume_improvements")
                resume.ats_score = ats_score
                resume.ai_feedback = ai_feedback
            except Exception as e:
                logger.exception("Failed during resume section storage or ATS scoring")
                raise HTTPException(
                    status_code=500, detail="Resume section processing failed"
                ) from e
        else:
            logger.info(
                "PersonalInfo already exists and force update is not set — skipping resume data population."
            )

        await db.flush()
        await db.refresh(resume)
        await db.commit()

        try:
            if background_tasks:
                background_tasks.add_task(resume_vectorstore_v2, user_id, db)
                background_tasks.add_task(recommend_jobs_combined, user_id, db)
                # background_tasks.add_task(create_student_courses, db, user_id)
        except Exception as e:
            logger.warning(f"Failed to schedule background tasks: {str(e)}")
            return {
                "ats_score": ats_score,
                "ai_feedback": ai_feedback,
                "warning": "Resume uploaded, but some background tasks failed to schedule.",
            }

        logger.info(f"Resume uploaded for student {student.student_id} at {file_path}")
        return {"ats_score": ats_score, "ai_feedback": ai_feedback}

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.exception("Resume upload failed")
        raise HTTPException(
            status_code=500, detail="Resume upload failed due to internal error"
        ) from e


async def get_resumes_by_user_id(
    user_id: UUID, db: AsyncSession
) -> list[ResumeVersion]:
    """
    Retrieve all resumes of type 'Uploaded' for a specific user.

    Args:
        user_id (UUID): UUID of the user.
        db (AsyncSession): Asynchronous DB session.

    Returns:
        list[ResumeVersion]: Resume version objects associated with the user.
    """
    try:
        student_result = await db.execute(
            select(Student).where(Student.user_id == user_id)
        )
        student = student_result.scalar_one_or_none()
        if not student:
            return []

        result = await db.execute(
            select(ResumeVersion)
            .where(
                ResumeVersion.student_id == student.student_id,
                ResumeVersion.resume_type == "Uploaded",
            )
            .order_by(ResumeVersion.created_at.desc())
        )
        return result.scalars().all()

    except Exception as e:
        logger.exception(f"Failed to retrieve resumes for user {user_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Internal error fetching user resumes"
        )


async def get_all_resumes(db: AsyncSession) -> list[tuple[ResumeVersion, UUID]]:
    """
    Retrieve all resume versions across all users.

    Args:
        db (AsyncSession): Asynchronous DB session.

    Returns:
        list[tuple[ResumeVersion, UUID]]: List of resumes with associated user IDs.
    """
    try:
        result = await db.execute(
            select(ResumeVersion, Student.user_id)
            .join(Student, ResumeVersion.student_id == Student.student_id)
            .order_by(ResumeVersion.created_at.desc())
        )
        return result.all()
    except Exception as e:
        logger.exception("Failed to fetch all resumes: %s", e)
        raise HTTPException(
            status_code=500, detail="Internal error fetching all resumes"
        )


async def calculate_ats_score(resume_json: dict) -> int:
    """
    Calculates a simplified ATS (Applicant Tracking System) score based on resume content.

    The scoring is done based on presence and quality of certain key sections in the resume,
    including: skills, education, experience, projects, certifications, and formatting issues.

    Positive points are awarded for well-structured content, and negative points for formatting
    elements that typically hinder ATS parsing (e.g., images, tables, icons, multi-column layouts).

    Args:
        resume_json (dict): Parsed resume data with structured fields.

    Returns:
        int: Calculated ATS score between 0 and 100.

    Used in:
        create_resume_version_profile_V2
    """
    logger.info("Called the calculate_ats_score function")
    ats_score = 0

    # Early return if resume has poor descriptions
    if not resume_json.get("valid_descriptions", False):
        logger.info("Invalid descriptions — ATS score cannot be calculated accurately.")
        return 20  # Return base score if descriptions are bad

    # --- Positive scoring ---

    # +20 for skills
    skills = resume_json.get("skills", {})
    if skills and any(skills.values()):
        ats_score += 20

    # +5 for having an objective/summary
    if resume_json.get("objective"):
        ats_score += 5

    # +10 for education section
    if resume_json.get("education"):
        ats_score += 10

    # +15 for valid experience entry
    experience = resume_json.get("experience", [])
    if experience and experience[0].get("role"):
        ats_score += 15

    # +10 for certifications or courses
    extra_fields = resume_json.get("extra_fields", {})
    if extra_fields.get("certifications") or extra_fields.get("courses"):
        ats_score += 10

    # +15–25 based on number of projects
    projects = resume_json.get("projects", [])
    if len(projects) == 1:
        ats_score += 15
    elif len(projects) >= 2:
        ats_score += 25

    # +5 for publications
    if resume_json.get("publications"):
        ats_score += 5

    # +10 for achievements
    if resume_json.get("achievements"):
        ats_score += 10

    # --- Negative scoring (penalties) ---

    # -8 for having an image (ATS usually can't parse images)
    if resume_json.get("image_present"):
        ats_score -= 8

    # -6 for tables (complex parsing)
    if resume_json.get("tables_present"):
        ats_score -= 6

    # -4 for decorative icons
    if resume_json.get("icons_present"):
        ats_score -= 4

    # -5 for multi-column layout
    if resume_json.get("multi_column"):
        ats_score -= 5

    # -5 for unclear or vague project descriptions
    if not resume_json.get("project_clarity", True):
        ats_score -= 5

    logger.info(f"Final ATS Score: {ats_score}")
    return ats_score


async def download_file(version_id: UUID, db: AsyncSession):
    """
    Downloads the PDF file associated with a resume version.

    - Looks up the resume version by ID.
    - Attempts to stream the file stored in the database (as byte array).
    - Returns the file as a downloadable PDF attachment.

    Args:
        version_id (UUID): The UUID of the resume version.
        db (AsyncSession): Async SQLAlchemy session.

    Returns:
        StreamingResponse: Streamed PDF file if available.

    Raises:
        HTTPException: 404 if resume not found, 422 if file is missing.
    """
    try:
        result = await db.execute(
            select(ResumeVersion).where(ResumeVersion.version_id == version_id)
        )
        resume_version = result.scalar_one_or_none()

        if not resume_version:
            raise HTTPException(status_code=404, detail="Resume Version Not Found")

        if resume_version.file and len(resume_version.file) > 0:
            return StreamingResponse(
                BytesIO(resume_version.file),
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="{resume_version.resume_name or "resume.pdf"}"'
                },
            )

        raise HTTPException(
            status_code=422,
            detail="No valid file found: neither a usable file path nor stored file content in DB.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to download resume file")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while processing the resume download.",
        ) from e


async def delete_resume_and_files(user_id: UUID, db: AsyncSession):
    """
    Deletes all resume versions and associated files for a student.
    Also removes the user's resume vector from Qdrant (async).

    Args:
        user_id (UUID): User's UUID.
        db (AsyncSession): Async DB session.

    Returns:
        dict: Summary of deletion results.
    """
    try:
        # Step 1: Fetch student by user_id
        result = await db.execute(select(Student).where(Student.user_id == user_id))
        student = result.scalar_one_or_none()

        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        student_id = student.student_id

        # Step 2: Get resume versions
        result = await db.execute(
            select(ResumeVersion).where(ResumeVersion.student_id == student_id)
        )
        resume_versions = result.scalars().all()

        if not resume_versions:
            return {"message": "No resume versions found for this student."}

        # Step 3: Delete associated files from disk
        deleted_files = []
        for rv in resume_versions:
            if rv.file_path and os.path.isfile(rv.file_path):
                try:
                    os.remove(rv.file_path)
                    deleted_files.append(rv.file_path)
                except Exception as e:
                    logger.warning(f"Failed to delete file {rv.file_path}: {e}")

        # Step 4: Delete resume rows from DB
        try:
            await db.execute(
                ResumeVersion.__table__.delete().where(
                    ResumeVersion.student_id == student_id
                )
            )
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.exception("Failed to delete resume versions")
            raise HTTPException(status_code=500, detail=f"DB deletion failed: {str(e)}")

        # Step 5: Delete vector from Qdrant
        try:
            vector_delete_result = await qdrant_client.delete(
                collection_name="resume_vectors",  # replace with your collection name
                points_selector={
                    "filter": {
                        "must": [{"key": "user_id", "match": {"value": str(user_id)}}]
                    }
                },
            )
        except Exception as e:
            logger.warning(f"Failed to delete vector for user {user_id}: {e}")
            vector_delete_result = {"error": "Vector deletion failed"}

        return {
            "message": f"Deleted {len(resume_versions)} resume versions and their files.",
            "deleted_files": deleted_files,
            "vector_delete_result": vector_delete_result,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error in resume deletion")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while deleting resumes.",
        ) from e
