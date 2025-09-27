import pandas as pd
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import StudentBatch
from app.services.resume_service import create_resume_version_profile
from app.services.student_courses_service import create_student_courses
from app.services.resume_screener_service import (
    resume_vectorstore_v2,
    recommend_jobs_combined,
)
from app.utils.logger_config import logger
from io import BytesIO
import zipfile
import os
from fastapi import UploadFile
from typing import Dict, List, Tuple
from sqlalchemy import select
import asyncio


async def create_excel_with_credentials(data: List[Dict]) -> BytesIO:
    """
    Asynchronously creates an Excel file containing student credentials in memory.

    Args:
        data (List[Dict]): A list of dictionaries representing student credential rows.

    Returns:
        BytesIO: In-memory Excel file stream.
    """
    return await asyncio.to_thread(_generate_excel_in_memory, data)



def _generate_excel_in_memory(data: List[Dict]) -> BytesIO:
    """
    Synchronously creates an Excel file in memory using pandas and xlsxwriter.

    Args:
        data (List[Dict]): List of rows as dictionaries to include in the Excel sheet.

    Returns:
        BytesIO: In-memory Excel file.
    """
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return output


async def create_resume_version_profile_wrapper(
    db: AsyncSession,
    user_id: UUID,
    resume_type: str,
    resume_name: str,
    source_resume_id: UUID = None,
    file: UploadFile = None,
):
    """
    Creates a new resume version for the given user and triggers post-processing tasks
    such as resume vectorization and job recommendations concurrently.

    Args:
        db (AsyncSession): Async database session.
        user_id (UUID): User ID associated with the resume.
        resume_type (str): Type of the resume (e.g., 'final', 'draft').
        resume_name (str): Human-readable name for the resume version.
        source_resume_id (UUID, optional): Resume ID to clone from.
        file (UploadFile, optional): Uploaded resume file to process.

    Returns:
        dict | ResumeVersion: Resume version data or error dictionary.
    """
    try:
        result = await create_resume_version_profile(
            db=db,
            user_id=user_id,
            resume_type=resume_type,
            resume_name=resume_name,
            source_resume_id=source_resume_id,
            file=file,
            background_tasks=None,
        )

        await asyncio.gather(
            resume_vectorstore_v2(user_id, db),
            recommend_jobs_combined(user_id, db),
            # create_student_courses(db, user_id),
        )

        return result

    except Exception as e:
        logger.error(f"Error in resume post-processing for user {user_id}: {e}")
        return {"error": str(e)}



def map_excel_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Maps user-provided Excel column headers to internal standard field names.

    Args:
        df (pd.DataFrame): DataFrame loaded from the uploaded Excel sheet.

    Returns:
        pd.DataFrame: Renamed DataFrame with standardized column names.
    """
    column_mapping = {
        "full_name": ["name", "student name", "fullname", "full name"],
        "email": ["email", "mail", "mail id", "email id"],
        "student_id": ["student id", "id", "roll number", "roll no", "reg no"],
        "branch": ["department", "branch", "dept"],
        "batch": ["batch", "graduation year", "passout year", "year"],
    }

    reverse_map = {}
    lower_cols = {col.strip().lower(): col for col in df.columns}
    for std_col, aliases in column_mapping.items():
        for alias in aliases:
            if alias.lower() in lower_cols:
                reverse_map[lower_cols[alias.lower()]] = std_col
                break

    return df.rename(columns=reverse_map)



async def extract_resumes_from_zip_in_memory(
    zip_file: UploadFile, expected_ids: List[str]
) -> Tuple[Dict[str, bytes], List[str]]:
    """
    Asynchronously extracts resumes from an uploaded ZIP file in memory and matches them to expected student IDs.

    Args:
        zip_file (UploadFile): Uploaded ZIP file containing PDF resumes.
        expected_ids (List[str]): List of expected student IDs from Excel.

    Returns:
        Tuple[Dict[str, bytes], List[str]]:
            - Mapping of matched student IDs (lowercased) to their resume file bytes.
            - List of student IDs for which resumes were not found.
    """
    return await asyncio.to_thread(_extract_zip_sync, zip_file, expected_ids)



def _extract_zip_sync(
    zip_file: UploadFile, expected_ids: List[str]
) -> Tuple[Dict[str, bytes], List[str]]:
    """
    Extracts and matches resume PDFs from a ZIP file to the given list of student IDs.

    Args:
        zip_file (UploadFile): In-memory uploaded ZIP file.
        expected_ids (List[str]): List of student IDs expected to be present in ZIP.

    Returns:
        Tuple[Dict[str, bytes], List[str]]:
            - Dictionary mapping student_id -> resume bytes.
            - List of student_ids missing from the ZIP file.
    """
    resume_map: Dict[str, bytes] = {}
    expected_ids_lower = [str(sid).strip().lower() for sid in expected_ids]

    zip_bytes = zip_file.file.read()
    zip_file.file.close()

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zip_ref:
        for file_name in zip_ref.namelist():
            if not file_name.lower().endswith(".pdf"):
                logger.warning(f"Skipping non-PDF file in ZIP: {file_name}")
                continue

            student_id = (
                os.path.splitext(os.path.basename(file_name))[0].strip().lower()
            )

            if student_id in expected_ids_lower:
                resume_map[student_id] = zip_ref.read(file_name)
                logger.debug(f"Matched resume to student_id: {student_id}")
            else:
                logger.warning(f"File '{file_name}' does not match any student ID")

    missing_ids = [sid for sid in expected_ids_lower if sid not in resume_map]
    return resume_map, missing_ids



async def get_or_create_student_batch(
    db: AsyncSession,
    college_id: UUID,
    batch_year: int,
    department: str = None,
    section: str = None,
) -> UUID:
    """
    Retrieves a student batch for the given criteria or creates a new one if it doesn't exist.

    Args:
        db (AsyncSession): Async SQLAlchemy session.
        college_id (UUID): College identifier.
        batch_year (int): Year of graduation or batch.
        department (str, optional): Department or branch name.
        section (str, optional): Section within the department.

    Returns:
        UUID: The unique ID of the existing or newly created batch.
    """
    stmt = select(StudentBatch).filter_by(
        college_id=college_id,
        batch_year=batch_year,
        department=department,
        section=section,
    )
    result = await db.execute(stmt)
    batch = result.scalar_one_or_none()

    if not batch:
        batch = StudentBatch(
            college_id=college_id,
            batch_year=batch_year,
            department=department,
            section=section,
        )
        db.add(batch)
        await db.flush()

    return batch.batch_id

