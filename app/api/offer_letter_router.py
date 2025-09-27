import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database.db import get_db

from app.database.models import Student, JobPosting, PersonalInfo, EmployerProfile

from app.utils.settings import settings
from app.schemas.offer_letter_schemas import (
    EmployerPostOfferLetterRequest,
    StudentPostOfferLetterRequest,
    StudentOfferLetterOut,
    EmployerOfferLetterOut,
    OfferLetterSchema,
    OfferLetterTemplateOut,
)
import app.services.offer_letter_services as offer_letter_services

router = APIRouter(prefix="/api/offerletter", tags=["Offer Letter"])

os.makedirs(settings.OFFER_LETTERS, exist_ok=True)


@router.get("/populate-templates")
async def populate():
    await offer_letter_services.populate_templates()
    return


@router.get("/templates", response_model=List[OfferLetterTemplateOut])
async def get_templates(db: AsyncSession = Depends(get_db)):
    """
    Retrieve all available offer letter templates.

    Returns:
        List[OfferLetterTemplateOut]: A list of offer letter templates.

    Raises:
        HTTPException: If templates cannot be retrieved due to a database error or unexpected failure.
    """
    try:
        templates = await offer_letter_services.template(db, all=True)
        return [
            OfferLetterTemplateOut.model_validate(template) for template in templates
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching offer letter templates: {str(e)}",
        )


@router.post("/employer/generate", response_model=OfferLetterSchema)
async def generate(
    request: EmployerPostOfferLetterRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Generate and save a new offer letter for a student based on a job posting.
    """

    student = await db.scalar(
        select(Student).where(Student.user_id == request.student_id)
    )
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with user_id '{request.student_id}' not found.",
        )

    student_info = await db.scalar(
        select(PersonalInfo).where(PersonalInfo.student_id == student.student_id)
    )
    if not student_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PersonalInfo for student_id '{student.student_id}' not found.",
        )

    posting = await db.scalar(
        select(JobPosting).where(JobPosting.job_id == request.job_id)
    )
    if not posting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"JobPosting with job_id '{request.job_id}' not found.",
        )

    template = await offer_letter_services.template(db, template_id=request.template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Offer letter template '{request.template_id}' not found.",
        )

    try:
        data = await offer_letter_services.get_offer_data(
            student_info, posting, request.start_date
        )

        doc = await offer_letter_services.fill_offer_letter(template.template_file, data)

        letter = await offer_letter_services.save_offer_letter(
            db, student.student_id, posting.job_id, doc
        )

        return OfferLetterSchema.model_validate(letter)

    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error rendering offer letter: {str(ve)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error generating offer letter: {str(e)}",
        )


@router.get("/employer/get/{user_id}", response_model=List[EmployerOfferLetterOut])
async def get_offer_letters(user_id: str, db: AsyncSession = Depends(get_db)):
    """
    Retrieve all offer letters created by a given employer.

    Args:
        user_id (str): The employer's user ID.
        db (AsyncSession): Async database session dependency.

    Returns:
        List[EmployerOfferLetterOut]: A list of offer letters associated with the employer.

    Raises:
        HTTPException 404: If no EmployerProfile is found for the given user_id.
        HTTPException 500: For any unexpected errors while fetching data.
    """
    # 1. Verify employer exists
    employer = await db.scalar(
        select(EmployerProfile).where(EmployerProfile.user_id == user_id)
    )
    if not employer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employer with user_id '{user_id}' not found.",
        )

    try:
        # 2. Fetch and return offer letters
        letters = await offer_letter_services.get_offer_letters(
            db, unique_id=employer.employer_id, role_type="employee"
        )

        data = await offer_letter_services.get_offer_letter_data(
            db, letters, unique_id=employer.employer_id, role_type="employee"
        )

        return [EmployerOfferLetterOut.model_validate(unit) for unit in data]

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving offer letters: {str(e)}",
        )


@router.post("/student/sign", response_model=OfferLetterSchema)
async def sign(request: StudentPostOfferLetterRequest, db: AsyncSession = Depends(get_db)):
    """
    Sign an existing offer letter on behalf of the student.

    This endpoint will:
    1. Look up the Student by the provided user_id.
    2. Delegate to the service layer to append the student's signature,
       update the letter status, and persist the change.
    3. Return the updated OfferLetter record.

    Args:
        request (StudentPostOfferLetterRequest): Contains `user_id` and `job_id`.
        db (AsyncSession): Injected SQLAlchemy async session.

    Returns:
        OfferLetterOut: The signed offer letter, with updated status.

    Raises:
        HTTPException 404: If the student or the offer letter cannot be found.
        HTTPException 400: If the signing process fails due to invalid data.
        HTTPException 500: For any unexpected server error.
    """
    try:
        student = await db.scalar(
            select(Student).where(Student.user_id == request.user_id)
        )
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Student with user_id '{request.user_id}' not found.",
            )

        signed_letter = await offer_letter_services.sign_offer_letter(
            db, student_id=student.student_id, job_id=request.job_id
        )
        if not signed_letter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Offer letter for student_id '{student.student_id}' "
                    f"and job_id '{request.job_id}' not found."
                ),
            )

        # Optional: trigger post-signing workflow
        # await acceptance_workflow_services.hire(request.user_id, request.job_id)

        return OfferLetterSchema.model_validate(signed_letter)

    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error signing offer letter: {str(ve)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during signing: {str(e)}",
        )



@router.get("/student/get/{user_id}", response_model=List[StudentOfferLetterOut])
async def get_student_offers(user_id: str, db: AsyncSession = Depends(get_db)):
    """
    Retrieve all offer letters available to a student.

    This endpoint will:
    1. Look up the Student by the provided user_id.
    2. Fetch all offer letters linked to that student.
    3. Return the list of signed or unsigned letters.

    Args:
        user_id (str): The student’s user ID.
        db (AsyncSession): Injected SQLAlchemy async session.

    Returns:
        List[StudentOfferLetterOut]: A list of the student’s offer letters.

    Raises:
        HTTPException 404: If the student cannot be found.
        HTTPException 500: For any unexpected server error.
    """
    # 1. Verify the student exists
    student = await db.scalar(
        select(Student).where(Student.user_id == user_id)
    )
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with user_id '{user_id}' not found.",
        )

    try:
        # 2. Fetch the student’s offer letters
        letters = await offer_letter_services.get_offer_letters(
            db, unique_id=student.student_id, role_type="student"
        )

        data = await offer_letter_services.get_offer_letter_data(
            db, letters, unique_id=student.student_id, role_type="student"
        )

        # 3. Convert to DTOs and return
        return [StudentOfferLetterOut.model_validate(unit) for unit in data]

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving student offer letters: {str(e)}",
        )


@router.get("/view-template/{template_id}", response_class=FileResponse)
async def view_template(template_id: str, db: AsyncSession = Depends(get_db)):
    """
    Stream the raw .docx template file for the given template_id.

    Args:
        template_id (str): UUID of the template to view.
        db (AsyncSession): Injected SQLAlchemy async session.

    Returns:
        FileResponse: Streaming response of the .docx file.

    Raises:
        HTTPException 404: If the template record or file is not found.
        HTTPException 500: For any unexpected errors.
    """
    try:
        response = await offer_letter_services.read_template(db, template_id)
        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error retrieving template: {str(e)}"
        )


@router.get("/view-letter/{letter_id}", response_class=FileResponse)
async def view_letter(letter_id: str, db: AsyncSession = Depends(get_db)):
    """
    Stream the signed or unsigned offer letter document for the given letter_id.

    Args:
        letter_id (str): UUID of the offer letter to view.
        db (AsyncSession): Injected SQLAlchemy async session.

    Returns:
        FileResponse: Streaming response of the .docx file.

    Raises:
        HTTPException 404: If the offer letter record or file is not found.
        HTTPException 500: For any unexpected errors.
    """
    try:
        response = await offer_letter_services.read_letter(db, letter_id)
        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error retrieving letter: {str(e)}"
        )
