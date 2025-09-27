from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from sqlalchemy import desc, select
from uuid import UUID
from app.utils.logger_config import logger
from app.database.models.job_applications_models import JobApplication
from app.database.models.students_models import Student
from app.services.user_service import get_structured_resume_data

from io import BytesIO
import pandas as pd
import uuid
from app.database.models.users_models import User
from app.database.models.resume_versions_models import ResumeVersion
from app.database.models.job_postings_models import JobPosting


async def get_student_applications(job_id: UUID, db: AsyncSession):
    try:
        # 1. Fetch applications for the given job_id
        query = (
            select(JobApplication)
            .filter(JobApplication.job_id == job_id)
            .order_by(desc(JobApplication.fitment_score))
        )
        result = await db.execute(query)
        applications = result.scalars().all()

        if not applications:
            logger.info("No Job applications found.")
            return []

        result = []
        seen_students = set()

        for app in applications:
            student_id = app.student_id
            if student_id in seen_students:
                continue
            seen_students.add(student_id)

            # 2. Get student and associated user_id
            student_query = select(Student).filter(Student.student_id == student_id)
            student_result = await db.execute(student_query)
            student = student_result.scalars().first()

            if not student:
                logger.info(f"Student not found for student_id {student_id}")
                continue

            user_id = student.user_id

            try:
                # 3. Get structured resume data
                resume_data = await get_structured_resume_data(user_id, db)
                resume_data["job_id"] = str(app.job_id)
                resume_data["status"] = app.status
                resume_data["matching_score"] = app.fitment_score
                result.append(resume_data)

            except HTTPException as e:
                logger.info(f"Failed to get resume for user {user_id}: {e.detail}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error for user {user_id}: {str(e)}")
                continue

        return result

    except Exception as e:
        logger.error(f"Failed to fetch student applications: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


async def get_student_applications_count(job_id: UUID, db: AsyncSession):
    try:
        query = select(JobApplication).filter(JobApplication.job_id == job_id)
        result = await db.execute(query)
        applications = result.scalars().all()

        if not applications:
            logger.info("No Job applications found.")
            return {"total_applications": 0}

        seen_students = set()

        for app in applications:
            student_id = app.student_id
            if student_id in seen_students:
                continue
            seen_students.add(student_id)

        return {"total_applications": len(seen_students)}

    except Exception as e:
        logger.error(f"Failed to fetch student applications: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


async def export_applicants_to_excel(db: AsyncSession, job_id: uuid.UUID) -> BytesIO:
    """
    Fetches applicant data for a specific job depending on the data available about the applicants and exports it to an Excel file with resume download links.

    Args:
        db (AsyncSession): Async SQLAlchemy session.
        job_id (uuid.UUID): The ID of the job posting.

    Returns:
        BytesIO: An Excel file in memory.
    """
    # Check if job exists
    job_exists = await db.scalar(select(JobPosting).where(JobPosting.job_id == job_id))
    if not job_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job posting not found"
        )

    # Fetch applicants with related user and resume data
    result = await db.execute(
        select(User.full_name, User.email, ResumeVersion.version_id, JobPosting.title)
        .join(Student, Student.user_id == User.user_id)
        .join(JobApplication, JobApplication.student_id == Student.student_id)
        .join(
            ResumeVersion, ResumeVersion.version_id == JobApplication.resume_version_id
        )
        .join(JobPosting, JobPosting.job_id == JobApplication.job_id)
        .where(JobApplication.job_id == job_id)
    )

    rows = result.all()

    if not rows:
        # Create Excel with a note about no applicants
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df = pd.DataFrame(
                {
                    "Notice": [
                        "No applicants yet. We’ll notify you shortly when an applicant applies."
                    ]
                }
            )
            df.to_excel(writer, index=False, sheet_name="Applicants")
        output.seek(0)
        return output

    # Format data into DataFrame
    data = []
    for row in rows:
        data.append(
            {
                "student_name": row.full_name,
                "student_email": row.email,
                "resume": f"Download Resume ({row.version_id})",
                "job_title": row.title,
                "version_id": row.version_id,
            }
        )

    df = pd.DataFrame(data)

    # Create Excel in-memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        visible_df = df[["student_name", "student_email", "resume", "job_title"]]
        visible_df.to_excel(writer, index=False, sheet_name="Applicants")

        workbook = writer.book
        worksheet = writer.sheets["Applicants"]
        url_format = workbook.add_format({"font_color": "blue", "underline": 1})

        for i, col in enumerate(visible_df.columns):
            max_width = max(visible_df[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.set_column(i, i, max_width)

        for row_num, version_id in enumerate(df["version_id"]):
            link = f"https://your-api-url/resumes/{version_id}"  # Replace with actual base URL
            worksheet.write_url(
                row_num + 1,
                2,  # 'resume' column index
                link,
                url_format,
                df["resume"][row_num],
            )

    output.seek(0)
    return output
