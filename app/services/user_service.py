import os
from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional, Any
import asyncio
import aiofiles
from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse
from passlib.context import CryptContext
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from starlette.status import HTTP_404_NOT_FOUND

from app.database.models import (
    Aspiration,
    Certification,
    CompanyExperience,
    Education,
    EmployerProfile,
    Language,
    PersonalInfo,
    Projects,
    Skill,
    SocialProfile,
    Student,
    User,
    WorkExperience,
    CampusPlacementOfficer,
    Company
)
from app.schemas.user_schemas import ProfileUpdateSchema
from app.utils.logger_config import logger
from app.utils.settings import settings
from app.utils.db_session_utils import run_with_new_session
from sqlalchemy import select
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def create_user(user_data: dict, profile_image: Optional[UploadFile], db: AsyncSession):
    logger.info("Attempting to create user: %s", user_data["email"])

    # Check for duplicates
    result = await db.execute(select(User).filter(User.email == user_data["email"]))
    existing = result.scalars().first()
    if existing:
        logger.warning("User with email %s already exists", user_data["email"])
        raise HTTPException(status_code=400, detail="Email already registered")

    user_id = uuid4()
    file_path = None

    # Optional profile image handling
    if profile_image:
        os.makedirs(settings.PROFILE_IMG_DIR, exist_ok=True)
        _, ext = os.path.splitext(profile_image.filename)
        ext = ext.lower() or ".jpg"
        filename = f"{user_id}{ext}"
        file_path = os.path.join(settings.PROFILE_IMG_DIR, filename)

        async with aiofiles.open(file_path, "wb") as buffer:
            content = await profile_image.read()
            await buffer.write(content)

    # Hash password
    hashed_password = pwd_context.hash(user_data["password"])

    # Create base User
    new_user = User(
        user_id=user_id,
        email=user_data["email"],
        full_name=user_data["full_name"],
        password_hash=hashed_password,
        role=user_data["role"],
        profile_img_path=file_path,
    )
    db.add(new_user)

    # === Handle Student Role ===
    if user_data["role"] == "Student":
        sp = user_data.get("student_profile")
        if not sp:
            logger.error("Student role requires student_profile input")
            raise HTTPException(
                status_code=422, detail="Student profile data is required"
            )

        student_id = uuid4()
        new_student = Student(
            student_id=student_id,
            user_id=user_id,
            email=sp["email"],
        )
        db.add(new_student)

        # Add aspirations
        for text in sp.get("aspiration", []):
            aspiration_entry = Aspiration(
                aspiration_id=uuid4(),
                student_id=student_id,
                aspiration_text=text.strip(),
            )
            db.add(aspiration_entry)
        logger.info("Created student profile and aspirations for user %s", user_data["email"])

    # === Handle Employer Role ===
    elif user_data["role"] == "Employer":
        ep = user_data.get("employer_profile")
        if not ep:
            logger.error("Employer role requires employer_profile input")
            raise HTTPException(
                status_code=422, detail="Employer profile data is required"
            )

        new_employer = EmployerProfile(
            employer_id=uuid4(),
            user_id=user_id,
            company_name=ep["company_name"],
            company_type=ep["company_type"],
            company_description=ep["company_description"],
            logo_url=ep["logo_url"],
            website_url=ep["website_url"],
        )
        db.add(new_employer)
        logger.info("Created employer profile for user %s", user_data["email"])

    # === Handle Placement Officer Role ===
    elif user_data["role"] == "PlacementOfficer":
        pp = user_data.get("placement_officer_profile")
        if not pp or not pp.get("college_id"):
            logger.error("PlacementOfficer role requires placement_officer_profile with college_id")
            raise HTTPException(
                status_code=422,
                detail="Placement Officer profile with college_id is required",
            )

        new_officer = CampusPlacementOfficer(
            id=uuid4(),
            user_id=user_id,
            college_id=pp["college_id"],
            phone_number=pp.get("phone_number"),
        )
        db.add(new_officer)
        logger.info("Created placement officer profile for user %s", user_data["email"])

    # Finalize
    await db.commit()
    await db.refresh(new_user)
    logger.info("User created successfully with ID %s", user_id)

    return new_user

async def get_user_by_id(db: AsyncSession, user_id: UUID):
    """
    Fetch a user record by its UUID.

    Args:
        db (AsyncSession): Asynchronous database session.
        user_id (UUID): UUID of the user to retrieve.

    Returns:
        User: ORM user instance.

    Raises:
        HTTPException: If the user does not exist.
    """
    try:
        result = await db.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    except Exception as e:
        logger.exception(f"Failed to retrieve user by ID: {user_id}\nException: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def list_users(db: AsyncSession) -> list[User]:
    """
    Fetch all users from the database.

    Args:
        db (AsyncSession): Asynchronous database session.

    Returns:
        list[User]: List of user ORM objects.

    Raises:
        HTTPException: If a database error occurs.
    """
    try:
        result = await db.execute(select(User))
        users = result.scalars().all()
        return users
    except Exception as e:
        logger.exception(f"Failed to fetch user list.\nException: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def delete_user(db: AsyncSession, user_id: UUID) -> None:
    """
    Delete a user and related profile data depending on their role.

    Args:
        db (AsyncSession): Asynchronous database session.
        user_id (UUID): UUID of the user to delete.

    Returns:
        None

    Raises:
        HTTPException: If the user does not exist or on internal error.
    """
    try:
        user_result = await db.execute(select(User).where(User.user_id == user_id))
        user = user_result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        match user.role:
            case "Student":
                student_result = await db.execute(
                    select(Student).where(Student.user_id == user_id)
                )
                student = student_result.scalar_one_or_none()
                if student:
                    await db.delete(student)

            case "Employer":
                employer_result = await db.execute(
                    select(EmployerProfile).where(EmployerProfile.user_id == user_id)
                )
                employer = employer_result.scalar_one_or_none()
                if employer:
                    await db.delete(employer)

            case "CampusPlacementOfficer":
                cpo_result = await db.execute(
                    select(CampusPlacementOfficer).where(
                        CampusPlacementOfficer.user_id == user_id
                    )
                )
                cpo = cpo_result.scalar_one_or_none()
                if cpo:
                    await db.delete(cpo)

        await db.delete(user)
        await db.commit()

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error deleting user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def get_structured_resume_data(user_id: UUID, db: AsyncSession) -> dict:
    """
    Retrieve structured resume data for a student based on user_id.

    Args:
        user_id (UUID): The UUID of the student user.
        db (AsyncSession): Asynchronous database session.

    Returns:
        dict: A structured JSON representation of the resume.

    Raises:
        HTTPException: If the student or personal information is missing.
    """
    try:
        # Fetch Student
        student_result = await db.execute(
            select(Student).where(Student.user_id == user_id)
        )
        student = student_result.scalar_one_or_none()
        if not student:
            logger.info(f"Student not found: {user_id}")
            raise HTTPException(status_code=404, detail="Student not found")

        # Fetch Personal Info
        personal_result = await db.execute(
            select(PersonalInfo).where(PersonalInfo.student_id == student.student_id)
        )
        personal_info = personal_result.scalars().first()
        if not personal_info:
            logger.error(
                f"Personal info not found for student_id: {student.student_id}"
            )
            raise HTTPException(
                status_code=404, detail="No resume found for this student"
            )

        personal_info_id = personal_info.id

        # Concurrently fetch resume sections
        (
            experiences,
            skills_by_category,
            certifications,
            education,
            social_profiles,
            languages,
            projects,
        ) = await asyncio.gather(
            run_with_new_session(fetch_experiences, personal_info_id),
            run_with_new_session(fetch_skills, personal_info_id),
            run_with_new_session(fetch_certifications, personal_info_id),
            run_with_new_session(fetch_education, personal_info_id),
            run_with_new_session(fetch_social, personal_info_id),
            run_with_new_session(fetch_languages, personal_info_id),
            run_with_new_session(fetch_projects, personal_info_id),
        )

        structured = {
            "name": personal_info.full_name,
            "email": personal_info.email,
            "phone": personal_info.phone,
            "student_id": str(personal_info.student_id),
            "version_id": str(personal_info.version_id),
            "location": getattr(personal_info, "location", "") or "",
            "experience": experiences,
            "skills": skills_by_category,
            "education": education,
            "projects": projects,
            "extra_fields": {
                "certifications": certifications,
                "languages": languages,
            },
            **social_profiles,
        }

        return structured

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            f"Failed to retrieve structured resume data for user_id: {user_id} - {e}"
        )
        raise HTTPException(status_code=500, detail="Internal server error")


async def fetch_experiences(personal_info_id: UUID, db: AsyncSession):
    result = await db.execute(
        select(CompanyExperience).where(CompanyExperience.user_id == personal_info_id)
    )
    companies = result.scalars().all()
    return [
        {
            "company": c.company_name,
            "role": c.your_position,
            "dates": c.dates,
            "details": c.company_description or "",
        }
        for c in companies
    ]


async def fetch_skills(personal_info_id: UUID, db: AsyncSession):
    result = await db.execute(select(Skill).where(Skill.user_id == personal_info_id))
    skills = result.scalars().all()
    skills_by_category = {}
    for s in skills:
        if s.category not in skills_by_category:
            skills_by_category[s.category] = []
        skills_by_category[s.category].append(s.skill_name)
    return skills_by_category


async def fetch_certifications(personal_info_id: UUID, db: AsyncSession):
    result = await db.execute(
        select(Certification).where(Certification.user_id == personal_info_id)
    )
    certs = result.scalars().all()
    return [
        {
            "certification_name": c.certification_name,
            "issued_by": c.issued_by,
            "issue_date": c.issue_date.isoformat() if c.issue_date else None,
            "expiration_date": c.expiration_date.isoformat()
            if c.expiration_date
            else None,
        }
        for c in certs
    ]


async def fetch_education(personal_info_id: UUID, db: AsyncSession):
    result = await db.execute(
        select(Education).where(Education.user_id == personal_info_id)
    )
    education = result.scalars().all()
    return [
        {
            "institution": e.institution_name,
            "degree": e.degree,
            "dates": f"{e.start_date.year if e.start_date else ''} - {e.end_date.year if e.end_date else 'Present'}",
            "details": e.description or "",
        }
        for e in education
    ]


async def fetch_social(personal_info_id: UUID, db: AsyncSession):
    result = await db.execute(
        select(SocialProfile).where(SocialProfile.user_id == personal_info_id)
    )
    social = result.scalar_one_or_none()
    return {
        "personal_website": social.personal_website if social else None,
        "linkedin": social.linkedin if social else None,
        "github": social.github if social else None,
        "twitter": social.twitter if social else None,
    }


async def fetch_languages(personal_info_id: UUID, db: AsyncSession):
    result = await db.execute(
        select(Language).where(Language.user_id == personal_info_id)
    )
    langs = result.scalars().all()
    return [lang.language_name for lang in langs]


async def fetch_projects(personal_info_id: UUID, db: AsyncSession):
    result = await db.execute(
        select(Projects).where(Projects.user_id == personal_info_id)
    )
    projects = result.scalars().all()
    return [
        {
            "title": p.title,
            "dates": p.dates,
            "details": p.details or "",
        }
        for p in projects
    ]



async def upload_profile_image_service(
    user_id: UUID, file: UploadFile, db: AsyncSession
) -> dict:
    """
    Save and associate a profile image with the user.

    If a profile image already exists, it will be overwritten.

    Args:
        user_id (UUID): UUID of the user.
        file (UploadFile): Uploaded image file.
        db (AsyncSession): Asynchronous database session.

    Returns:
        dict: A response containing the saved file path and user ID.

    Raises:
        HTTPException: If user is not found or file type is unsupported.
    """
    try:
        result = await db.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="User not found")

        ext = os.path.splitext(file.filename)[-1].lower()
        if ext not in settings.VALID_IMAGE_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Unsupported file type")

        os.makedirs(settings.UPLOAD_PROFILE_IMG_FOLDER, exist_ok=True)
        save_path = os.path.join(settings.UPLOAD_PROFILE_IMG_FOLDER, f"{user_id}{ext}")

        # Delete old file if extension has changed
        if user.profile_img_path and user.profile_img_path != save_path:
            try:
                if os.path.exists(user.profile_img_path):
                    os.remove(user.profile_img_path)
            except Exception as cleanup_err:
                logger.warning(f"Could not delete old profile image: {cleanup_err}")

        async with aiofiles.open(save_path, "wb") as out_file:
            content = await file.read()
            await out_file.write(content)

        user.profile_img_path = save_path
        await db.commit()

        logger.info(f"Profile image uploaded for user {user_id} -> {save_path}")

        return {"user_id": str(user_id), "profile_img_path": save_path}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error uploading profile image for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def get_profile_image(user_id: UUID, db: AsyncSession) -> FileResponse:
    """
    Retrieve the profile image file for a given user.

    Args:
        user_id (UUID): UUID of the user.
        db (AsyncSession): Asynchronous database session.

    Returns:
        FileResponse: The user's profile image file.

    Raises:
        HTTPException: If user, image path, or file is missing.
    """
    try:
        result = await db.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()

        if not user or not user.profile_img_path:
            raise HTTPException(status_code=404, detail="User or image not found")

        image_path = user.profile_img_path

        if not os.path.exists(image_path):
            raise HTTPException(status_code=404, detail="File not found on disk")

        ext = os.path.splitext(image_path)[-1].lower()
        mime_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
        }.get(ext, "application/octet-stream")

        logger.info(f"Serving profile image for user {user_id}: {image_path}")
        return FileResponse(path=image_path, media_type=mime_type)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving profile image for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Synchronous Code, still left it alive because i dint test the async code :)
# def update_user_profile(user_id: UUID, db: Session, profile_data: ProfileUpdateSchema):
#     # Retrieve student and personal info from the database
#     student = db.query(Student).filter(Student.user_id == user_id).first()

#     if not student:
#         raise HTTPException(status_code=404, detail="Student not found")

#     personal_info = (
#         db.query(PersonalInfo)
#         .filter(PersonalInfo.student_id == student.student_id)
#         .first()
#     )

#     if not personal_info:
#         raise HTTPException(status_code=404, detail="Personal info not found")

#     # Update PersonalInfo fields
#     if profile_data.name is not None:
#         personal_info.full_name = profile_data.name
#     if profile_data.email is not None:
#         personal_info.email = profile_data.email
#     if profile_data.phone is not None:
#         personal_info.phone = profile_data.phone
#     if profile_data.location is not None:
#         personal_info.location = profile_data.location
#     if profile_data.bio is not None:
#         personal_info.bio = profile_data.bio

#     # Update Education fields
#     education = (
#         db.query(Education).filter(Education.user_id == personal_info.id).first()
#     )
#     if education:
#         if profile_data.university is not None:
#             education.institution_name = profile_data.university
#         if profile_data.major is not None:
#             education.field_of_study = profile_data.major
#         if profile_data.graduationYear is not None:
#             try:
#                 education.end_date = datetime.strptime(
#                     profile_data.graduationYear, "%Y"
#                 )
#             except ValueError:
#                 raise HTTPException(
#                     status_code=400, detail="Invalid date format for graduation year."
#                 )

#     # Update Company Experience fields
#     company_exp = (
#         db.query(CompanyExperience)
#         .filter(CompanyExperience.user_id == personal_info.id)
#         .first()
#     )
#     if company_exp:
#         if profile_data.company is not None:
#             company_exp.company_name = profile_data.company
#         if profile_data.position is not None:
#             company_exp.your_position = profile_data.position
#         if profile_data.website is not None:
#             company_exp.company_website = profile_data.website

#     # Update Social Profiles fields
#     social = (
#         db.query(SocialProfile)
#         .filter(SocialProfile.user_id == personal_info.id)
#         .first()
#     )
#     if social:
#         if profile_data.linkedin is not None:
#             social.linkedin = profile_data.linkedin
#         if profile_data.github is not None:
#             social.github = profile_data.github
#         if profile_data.twitter is not None:
#             social.twitter = profile_data.twitter

#     # Commit changes to the database
#     db.commit()

#     # Return the updated profile data
#     return {
#         "name": personal_info.full_name or "",
#         "email": personal_info.email or student.email,
#         "phone": personal_info.phone or "",
#         "location": personal_info.location or "",
#         "university": education.institution_name if education else "",
#         "major": education.field_of_study if education else "",
#         "graduationYear": (
#             str(education.end_date.year) if education and education.end_date else ""
#         ),
#         "company": company_exp.company_name if company_exp else "",
#         "position": company_exp.your_position if company_exp else "",
#         "website": company_exp.company_website if company_exp else "",
#         "linkedin": social.linkedin if social else "",
#         "github": social.github if social else "",
#         "twitter": social.twitter if social else "",
#         "bio": personal_info.bio or "",
#     }

# Async Code:
async def update_user_profile(user_id: UUID, db: AsyncSession, profile_data: ProfileUpdateSchema):
    # Retrieve Student
    result = await db.execute(select(Student).filter(Student.user_id == user_id))
    student = result.scalars().first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Retrieve PersonalInfo
    result = await db.execute(select(PersonalInfo).filter(PersonalInfo.student_id == student.student_id))
    personal_info = result.scalars().first()
    if not personal_info:
        raise HTTPException(status_code=404, detail="Personal info not found")

    # Update PersonalInfo fields
    if profile_data.name is not None:
        personal_info.full_name = profile_data.name
    if profile_data.email is not None:
        personal_info.email = profile_data.email
    if profile_data.phone is not None:
        personal_info.phone = profile_data.phone
    if profile_data.location is not None:
        personal_info.location = profile_data.location
    if profile_data.bio is not None:
        personal_info.bio = profile_data.bio

    # Update Education fields
    result = await db.execute(select(Education).filter(Education.user_id == personal_info.id))
    education = result.scalars().first()
    if education:
        if profile_data.university is not None:
            education.institution_name = profile_data.university
        if profile_data.major is not None:
            education.field_of_study = profile_data.major
        if profile_data.graduationYear is not None:
            try:
                education.end_date = datetime.strptime(profile_data.graduationYear, "%Y")
            except ValueError:
                raise HTTPException(
                    status_code=400, detail="Invalid date format for graduation year."
                )

    # Update Company Experience
    result = await db.execute(select(CompanyExperience).filter(CompanyExperience.user_id == personal_info.id))
    company_exp = result.scalars().first()
    if company_exp:
        if profile_data.company is not None:
            company_exp.company_name = profile_data.company
        if profile_data.position is not None:
            company_exp.your_position = profile_data.position
        if profile_data.website is not None:
            company_exp.company_website = profile_data.website

    # Update Social Profiles
    result = await db.execute(select(SocialProfile).filter(SocialProfile.user_id == personal_info.id))
    social = result.scalars().first()
    if social:
        if profile_data.linkedin is not None:
            social.linkedin = profile_data.linkedin
        if profile_data.github is not None:
            social.github = profile_data.github
        if profile_data.twitter is not None:
            social.twitter = profile_data.twitter

    # Update Skills
    if profile_data.skills is not None:
        await db.execute(delete(Skill).where(Skill.user_id == personal_info.id))
        for skill_name in profile_data.skills:
            db.add(Skill(
                user_id=personal_info.id,
                skill_name=skill_name,
                category=None  # No category info in schema
            ))
    # Fetch updated skills
    result = await db.execute(select(Skill).filter(Skill.user_id == personal_info.id))
    skills = result.scalars().all()
    skills_list = [s.skill_name for s in skills]

    # Commit changes
    await db.commit()

    # Return updated profile
    return {
        "name": personal_info.full_name or "",
        "email": personal_info.email or student.email,
        "phone": personal_info.phone or "",
        "location": personal_info.location or "",
        "university": education.institution_name if education else "",
        "major": education.field_of_study if education else "",
        "graduationYear": str(education.end_date.year) if education and education.end_date else "",
        "company": company_exp.company_name if company_exp else "",
        "position": company_exp.your_position if company_exp else "",
        "website": company_exp.company_website if company_exp else "",
        "linkedin": social.linkedin if social else "",
        "github": social.github if social else "",
        "twitter": social.twitter if social else "",
        "bio": personal_info.bio or "",
        "skills": skills_list
    }

# function to get the profile strength
# --- Global scoring maps ---
STUDENT_SCORE_MAP = {
    "name": 5,
    "email": 5,
    "phone": 5,
    "experience": 15,
    "skills": 15,
    "education": 15,
    "projects": 15,
    "social_profile": 5,
    "location": 5,
    "profile_image": 15,
}

EMPLOYER_SCORE_MAP = {
    "name": 10,
    "email": 10,
    "profile_image": 15,
    "company_name": 10,
    "company_type": 10,
    "company_description": 20,
    "logo_url": 10,
    "website_url": 15,
}

#function to get the profile strength for student and employer
async def get_profile_strength_score(user_id: UUID, db: AsyncSession) -> dict[str, Any]:
    try:
        # Step 1: Get User with Profile Image
        user_result = await db.execute(select(User).filter(User.user_id == user_id))
        user = user_result.scalar_one_or_none()

        logger.info(f"USER MODEL BE LIKE: {user}")

        if not user:
            raise HTTPException(status_code=404, detail="No user exists with that ID")

        score = 0
        missing_fields = []

        if user.role.value == "student":
            student_result = await db.execute(
                select(Student)
                .filter(Student.user_id == user_id)
                .options(selectinload(Student.user))
            )
            student = student_result.scalar_one_or_none()

            if not student:
                raise HTTPException(status_code=404, detail="No student profile found.")

            personal_info_result = await db.execute(
                select(PersonalInfo).filter_by(student_id=student.student_id)
            )
            personal_info = personal_info_result.scalar_one_or_none()

            if not personal_info:
                raise HTTPException(status_code=404, detail="Resume data not found.")

            # === Profile Fields Check ===
            def check_and_score(field_value, field_key):
                nonlocal score
                if field_value:
                    score += STUDENT_SCORE_MAP[field_key]
                else:
                    missing_fields.append(field_key)

            check_and_score(personal_info.full_name, "name")
            check_and_score(personal_info.email, "email")
            check_and_score(personal_info.phone, "phone")
            check_and_score(getattr(personal_info, "location", None), "location")
            check_and_score(user.profile_img_path, "profile_image")

            # === Related Table Checks ===
            async def exists(model, filter_column, value):
                res = await db.execute(select(model).filter(filter_column == value))
                return res.first() is not None

            if await exists(CompanyExperience, CompanyExperience.user, personal_info):
                score += STUDENT_SCORE_MAP["experience"]
            else:
                missing_fields.append("experience")

            if await exists(Skill, Skill.user, personal_info):
                score += STUDENT_SCORE_MAP["skills"]
            else:
                missing_fields.append("skills")

            if await exists(Education, Education.user, personal_info):
                score += STUDENT_SCORE_MAP["education"]
            else:
                missing_fields.append("education")

            if await exists(Projects, Projects.user, personal_info):
                score += STUDENT_SCORE_MAP["projects"]
            else:
                missing_fields.append("projects")

            social_result = await db.execute(select(SocialProfile).filter_by(user=personal_info))
            social = social_result.scalar_one_or_none()
            if social and (social.personal_website or social.linkedin or social.github or social.twitter):
                score += STUDENT_SCORE_MAP["social_profile"]
            else:
                missing_fields.append("social_profile")

        elif user.role.value == "employer":
            def check_and_score_emp(value, key):
                nonlocal score
                if value:
                    score += EMPLOYER_SCORE_MAP[key]
                else:
                    missing_fields.append(key)

            check_and_score_emp(user.full_name, "name")
            check_and_score_emp(user.email, "email")
            check_and_score_emp(user.profile_img_path, "profile_image")

            employer_result = await db.execute(
                select(EmployerProfile).filter_by(user_id=user_id).options(selectinload(EmployerProfile.company))
            )
            employer_profile = employer_result.scalar_one_or_none()

            if not employer_profile or not employer_profile.company:
                missing_fields += ["company_name", "company_type", "company_description", "logo_url", "website_url"]
                return {"profile_strength_score": score, "missing_fields": missing_fields}

            company = employer_profile.company

            check_and_score_emp(company.name, "company_name")
            check_and_score_emp(company.type, "company_type")
            check_and_score_emp(company.description, "company_description")
            check_and_score_emp(company.logo_url, "logo_url")
            check_and_score_emp(company.website_url, "website_url")

        else:
            return {"message": "Profile scoring is not available for this user type."}

        return {"profile_strength_score": score, "missing_fields": missing_fields}

    except HTTPException:
        raise  # re-raise for FastAPI to catch normally

    except Exception as e:
        logger.exception(f"Unexpected error in profile strength scoring for user_id {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="An internal error occurred while scoring the profile.")