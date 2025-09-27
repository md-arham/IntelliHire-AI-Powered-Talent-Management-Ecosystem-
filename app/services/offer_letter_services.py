
import asyncio
from fastapi import HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from typing import Union, List
from io import BytesIO
import uuid
import aiofiles
from docx import Document
from python_docx_replace import docx_replace
from datetime import datetime
import os

from app.services.email_service import smtp_email_service

from app.database.db import async_session_maker
from app.utils.logger_config import ol_logger

from app.database.models import (
    OfferLetter, 
    OfferLetterEnum, 
    OfferLetterTemplate, 
    JobPosting,
    JobApplication,
    JobApplicationStatus,
    PersonalInfo,
    User,
    EmployerProfile
)

from app.utils.settings import settings 

# import app.services.acceptance_workflow_services as acceptance_workflow_services


async def populate_templates():
    try:
        os.makedirs(settings.OFFER_LETTER_TEMPLATES, exist_ok=True)
        ol_logger.info(f"Offer Templates folder: {settings.OFFER_LETTER_TEMPLATES}")
        template_files = os.listdir(settings.OFFER_LETTER_TEMPLATES)

        async with async_session_maker() as db:
            try:
                new_templates = []

                for file in template_files:
                    file_path = os.path.join(settings.OFFER_LETTER_TEMPLATES, file)

                    result = await db.execute(
                        select(OfferLetterTemplate).where(
                            OfferLetterTemplate.template_file == file_path
                        )
                    )
                    exists = result.scalar_one_or_none()

                    if not exists:
                        ol_logger.info(f"Adding file to db: {file_path}")
                        new_templates.append(
                            OfferLetterTemplate(
                                template_id=uuid.uuid4(),
                                template_file=file_path
                            )
                        )

                if new_templates:
                    db.add_all(new_templates)

                await db.commit()
            except SQLAlchemyError as e:
                await db.rollback()
                ol_logger.error(f"Database error while populating templates: {e}")
                return {"status": "error", "message": f"Database error: {str(e)}"}

    except Exception as e:
        ol_logger.error(f"Unhandled error in populate_templates: {e}")
        return {"status": "error", "message": f"Unhandled error: {str(e)}"}

    return {"status": "success", "message": ":)"}



async def template(
    db: AsyncSession,
    all: bool = False,
    template_id: Union[str, uuid.UUID] = None
) -> Union[List[OfferLetterTemplate], OfferLetterTemplate]:
    """
    Retrieve one or more offer letter templates from the database.

    Args:
        db (AsyncSession): Active SQLAlchemy async session.
        all (bool): Whether to fetch all templates.
        template_id (str or UUID, optional): ID of the template to fetch.

    Returns:
        List[OfferLetterTemplate] | OfferLetterTemplate: Retrieved template(s).

    Raises:
        HTTPException (404): If the specific template is not found.
        HTTPException (500): For any database-related errors.
    """
    try:
        if all:
            result = await db.execute(select(OfferLetterTemplate))
            return result.scalars().all()

        if not template_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="template_id must be provided if 'all' is False."
            )

        result = await db.execute(
            select(OfferLetterTemplate).where(OfferLetterTemplate.template_id == template_id)
        )
        template = result.scalar_one_or_none()

        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Offer letter template with ID '{template_id}' not found."
            )

        return template

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving template(s): {str(e)}"
        )

async def get_offer_data(student_info, posting, start_date):
    """
    Assemble contextual data for populating an offer letter template.

    Args:
        student_info: PersonalInfo instance containing student details.
        posting: JobPosting instance containing job details.
        start_date (str): Proposed start date provided by the employer.

    Returns:
        dict: A dictionary mapping placeholder keys to actual values.

    Raises:
        HTTPException (400): If student_info or posting is None.
        HTTPException (500): On unexpected failure.
    """
    try:
        if not student_info:
            raise HTTPException(status_code=400, detail="Student personal info not found.")
        if not posting:
            raise HTTPException(status_code=400, detail="Job posting not found.")

        keys = {
            "START_DATE": start_date,
            "EMPLOYEE_NAME": student_info.full_name,
            "PHONE": student_info.phone,
            "JOB_TITLE": posting.title,
            "SALARY": posting.salary_range,
            "COMPANY_NAME": posting.company_name,
            # "REQUIREMENTS": posting.requirements,
            "DATE": datetime.now().strftime("%c")
        }

        return keys

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error assembling offer data: {str(e)}")




async def fill_offer_letter(template_file, data):
    """
    Populate the given template file with the provided data.

    Args:
        template_file (str): Path to the .docx template file.
        data (dict): Dictionary of placeholders and their replacement values.

    Returns:
        Document: A python-docx Document object with the placeholders replaced.

    Raises:
        HTTPException (400): If the template file path is invalid or unreadable.
        HTTPException (500): On unexpected template rendering errors.
    """
    try:
        async with aiofiles.open(template_file, 'rb') as f:
            content = await f.read()

        doc = Document(BytesIO(content))
        docx_replace(doc, **data)
        return doc
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="Template file not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating offer letter: {str(e)}")


async def save_offer_letter(db: AsyncSession, student_id, job_id, doc: Document):
    """
    Persist the generated offer letter document asynchronously.

    Args:
        db (AsyncSession): SQLAlchemy async session.
        student_id (UUID): ID of the student receiving the offer.
        job_id (UUID): ID of the associated job posting.
        doc (Document): The populated offer letter document.

    Returns:
        OfferLetter: The newly saved OfferLetter database record.

    Raises:
        HTTPException (500): If file saving or database commit fails.
    """
    try:
        # Create file path
        file_name = f"{uuid.uuid4()}.docx"
        file_path = f"{settings.OFFER_LETTERS}/{file_name}"

        # Save to in-memory buffer
        buffer = BytesIO()
        doc.save(buffer)
        buffer.seek(0)

        # Write to file asynchronously
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(buffer.read())

        # Create DB record
        letter = OfferLetter(
            letter_id=uuid.uuid4(),
            student_id=student_id,
            job_id=job_id,
            letter_file=file_path,
            status=OfferLetterEnum.Unsigned
        )

        result = await db.execute(
            select(JobApplication).filter_by(student_id=student_id, job_id=job_id)
        )
        application = result.scalar_one_or_none()

        if application:
            application.status = JobApplicationStatus.Offered
            application.current_stage = "Offered"

        db.add(letter)
        await db.commit()
        await db.refresh(letter)
        return letter

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save offer letter: {str(e)}")



async def get_offer_letters(db: AsyncSession, unique_id, role_type: str):
    """
    Asynchronously fetch offer letters associated with a user, filtered by role.

    Args:
        db (AsyncSession): SQLAlchemy async database session.
        unique_id (UUID): ID of the student or employer.
        role_type (str): "student" or "employee".

    Returns:
        List[OfferLetter]: Offer letters related to the user.

    Raises:
        HTTPException (400): If role_type is invalid.
        HTTPException (500): On query failure.
    """
    try:
        if role_type == "student":
            result = await db.execute(
                select(OfferLetter).filter(OfferLetter.student_id == unique_id)
            )
            return result.scalars().all()

        elif role_type == "employee":
            subquery = select(JobPosting.job_id).filter(JobPosting.employer_id == unique_id)
            result = await db.execute(
                select(OfferLetter).filter(OfferLetter.job_id.in_(subquery))
            )
            return result.scalars().all()

        else:
            raise HTTPException(status_code=400, detail="Invalid role_type provided.")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch offer letters: {str(e)}")



async def sign_offer_letter(db: AsyncSession, student_id, job_id):
    """
    Asynchronously sign an offer letter by updating it with the student's name.

    Args:
        db (AsyncSession): SQLAlchemy async session.
        student_id (UUID): ID of the student signing.
        job_id (UUID): ID of the job.

    Returns:
        OfferLetter: Updated offer letter with signed status.

    Raises:
        HTTPException: For not found or internal failure.
    """
    try:
        # Fetch offer letter
        result = await db.execute(
            select(OfferLetter).filter(
                OfferLetter.job_id == job_id,
                OfferLetter.student_id == student_id
            )
        )
        letter = result.scalar_one_or_none()
        if not letter:
            raise HTTPException(status_code=404, detail="Offer letter not found.")

        # Fetch student info
        result = await db.execute(
            select(PersonalInfo).filter(PersonalInfo.student_id == student_id)
        )
        student_info = result.scalar_one_or_none()
        if not student_info:
            raise HTTPException(status_code=404, detail="Student information not found.")

        # Async read the file into memory
        try:
            async with aiofiles.open(letter.letter_file, mode="rb") as f:
                file_content = await f.read()
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Offer letter file not found.")

        # Load and modify in memory
        file_stream = BytesIO(file_content)
        doc = Document(file_stream)
        docx_replace(doc, SIGNATURE=student_info.full_name)

        # Save the modified document back asynchronously
        out_stream = BytesIO()
        doc.save(out_stream)
        out_stream.seek(0)

        async with aiofiles.open(letter.letter_file, mode="wb") as f:
            await f.write(out_stream.read())

        # Update DB
        letter.status = OfferLetterEnum.Signed

        # Update application
        result = await db.execute(
            select(JobApplication).filter(
                JobApplication.student_id == student_id,
                JobApplication.job_id == job_id
            )
        )
        application = result.scalar_one_or_none()
        if application:
            application.status = JobApplicationStatus.Hired
            application.current_stage = "Hired"

        await db.commit()
        await db.refresh(letter)

        # send email to employee saying the student signed the offer letter
        job_title, company_name, employer_email = await data_for_email(db, job_id)
        try:
            asyncio.create_task(
                offer_signed_email(employer_email, job_title, company_name, student_info.full_name)
            )
        except Exception as bg_err:
            ol_logger.error(f"Failed to schedule booking email task: {bg_err}", exc_info=True)


        return letter

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sign offer letter: {str(e)}")


async def data_for_email(
    db: AsyncSession,
    job_id: uuid.UUID,
) -> tuple[str, str, str, str]:
    """
    Fetch the data needed to send a booking notification email:
      - job_title
      - company_name
      - employer_email
      - student_name
    """

    # 1. Join JobPosting → EmployerProfile → User to get title, company, email
    stmt = (
        select(
            JobPosting.title,
            JobPosting.company_name,
            User.email
        )
        .join(EmployerProfile, EmployerProfile.employer_id == JobPosting.employer_id)
        .join(User, User.user_id == EmployerProfile.user_id)
        .where(JobPosting.job_id == job_id)
    )
    result = await db.execute(stmt)
    row = result.one_or_none()
    if row is None:
        raise ValueError(f"No job or employer found for job_id {job_id}")
    job_title, company_name, employer_email = row


    return job_title, company_name, employer_email

async def offer_signed_email(
    employer_email: str,
    job_title: str,
    company_name: str,
    student_name: str
) -> dict:
    """
    Notify the employer that a student has signed their offer.

    Args:
        employer_email (str): Employer’s email address.
        job_title (str): Title of the job offered.
        company_name (str): Name of the company.
        student_name (str): Full name of the student.

    Returns:
        dict: Result from smtp_send_email, e.g. {"success": True, ...}.
    """
    subject = f"{student_name} has signed the offer for {job_title}"
    
    text_content = (
        f"Hello,\n\n"
        f"We’re happy to let you know that {student_name} has signed the offer letter "
        f"for the position of {job_title} at {company_name}.\n\n"
        "You can now proceed with the next steps.\n\n"
        "Best regards,\n"
        f"{company_name} Hiring Platform"
    )
    
    html_content = (
        f"<p>Hello,</p>"
        f"<p>We’re happy to let you know that <strong>{student_name}</strong> has signed the "
        f"offer letter for the position of <em>{job_title}</em> at <strong>{company_name}</strong>.</p>"
        "<p>You can now proceed with the next steps.</p>"
        "<p>Best regards,<br>Your Hiring Platform</p>"
    )
    
    # Send via your SMTP helper
    response = await smtp_email_service.send_email(
        to_email=employer_email,
        subject=subject,
        html_content=html_content,
        text_content=text_content
    )
    ol_logger.info(response)
    return response


async def read_letter(db: AsyncSession, letter_id: str):
    """
    Asynchronously load an OfferLetter record and return its file as a FileResponse.

    Args:
        db (AsyncSession): SQLAlchemy async session.
        letter_id (str): UUID of the offer letter.

    Returns:
        FileResponse: Streaming response of the offer letter file.

    Raises:
        HTTPException: On missing record or file, or other errors.
    """
    try:
        result = await db.execute(
            select(OfferLetter).where(OfferLetter.letter_id == letter_id)
        )
        letter = result.scalar_one_or_none()

        if not letter:
            raise HTTPException(status_code=404, detail="Offer letter not found.")

        file_path = letter.letter_file
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Offer letter file not found on disk.")

        return FileResponse(
            path=file_path,
            filename=os.path.basename(file_path),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending offer letter file: {str(e)}")
    
async def read_template(db: AsyncSession, template_id: str):
    """
    Asynchronously load an OfferLetterTemplate record and return its file as a FileResponse.

    Args:
        db (AsyncSession): SQLAlchemy async session.
        template_id (str): UUID of the template.

    Returns:
        FileResponse: Stream of the template .docx file.

    Raises:
        HTTPException: On missing record, file not found, or I/O error.
    """
    try:
        result = await db.execute(
            select(OfferLetterTemplate).where(OfferLetterTemplate.template_id == template_id)
        )
        template = result.scalar_one_or_none()

        if not template:
            raise HTTPException(status_code=404, detail="Offer letter template not found.")

        file_path = template.template_file
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Template file not found on disk.")

        return FileResponse(
            path=file_path,
            filename=os.path.basename(file_path),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending template file: {str(e)}")


async def get_offer_letter_data(
    db: AsyncSession,
    letters: List[OfferLetter],
    unique_id: str,
    role_type: str
):
    """
    Asynchronously enrich raw OfferLetter ORM objects with additional display data for student or employer.

    Args:
        db (AsyncSession): Active async SQLAlchemy session.
        letters (List[OfferLetter]): List of OfferLetter instances.
        unique_id (UUID): ID of the student or employer.
        role_type (str): Either "student" or "employee".

    Returns:
        List[dict]: Each dict contains fields for StudentOfferLetterOut or EmployerOfferLetterOut.

    Raises:
        HTTPException: On invalid input or database error.
    """
    if role_type == "student" and unique_id:
        enriched = []
        try:
            for letter in letters:
                result = await db.execute(
                    select(JobPosting).where(JobPosting.job_id == letter.job_id)
                )
                posting = result.scalar_one_or_none()
                if not posting:
                    raise HTTPException(
                        status_code=500,
                        detail=f"JobPosting for job_id '{letter.job_id}' not found."
                    )

                if letter.offered_on is None:
                    try:
                        offered_on = datetime.fromtimestamp(
                            os.path.getmtime(letter.letter_file)
                        ).isoformat()
                    except Exception:
                        offered_on = None
                else:
                    offered_on = letter.offered_on.isoformat()

                enriched.append({
                    "job_title": posting.title,
                    "company_name": posting.company_name,
                    "offered_on": offered_on,
                    "offer_letter": letter
                })

            return enriched

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error assembling student offer data: {str(e)}"
            )

    elif role_type == "employee" and unique_id:
        return [{"offer_letter": letter} for letter in letters]

    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid role_type or missing unique_id"
        )