import os
import shutil
from datetime import datetime, timezone
from typing import List, Optional, Union
from uuid import uuid4
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
import re


from app.database.models.students_models import Student
from app.database.models.hackathon_models import (
    Hackathon,
    HackathonRegistration,
    ProblemStatement,
    Team,
    TeamStudent,
    Submission,
    Scoring,
)
from app.schemas.hackathon_schemas import (
    HackathonInResponse,
    ProblemStatementCreate,
    ProblemStatementUpdate,
    TeamStudentCreate,
    ScoringCreate,
    ScoringUpdate,
    TeamWithRegistrationCreate,
    TeamStudentResponse,
)
from app.utils.settings import settings
from fastapi.responses import FileResponse
from app.database.models.users_models import User
from app.utils.email_notifications import send_email
from app.utils.templates import TEMPLATES
from app.utils.logger_config import logger
from uuid import UUID

from app.utils.file_storage import save_file_locally, upload_file_to_s3
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.database.models import JobPosting
from app.utils.settings import ollama_async_client


class NotFoundException(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def clean_ai_description(raw: str) -> str:
    # Remove intro lines like: Here's a compelling description, etc.
    cleaned = re.sub(
        r"(?i)^here(?:’|')?s (?:a|an)?(?:.*?)?description(?: of .*?)?:\s*[\n\"]*",
        "",
        raw.strip(),
    )

    # Remove wrapping quotes if present
    cleaned = cleaned.strip().strip('"').strip("'")

    return cleaned.strip()


def sanitize_rules(rules: Optional[str | List[str]]) -> Optional[List[str]]:
    if isinstance(rules, str):
        return [r.strip() for r in rules.split(",") if r.strip()]
    return rules


async def generate_hackathon_description_with_ai(
    name: str,
    theme: str,
    mode: str,
    location: str,
    eligibility_criteria: str,
    rules: List[str],
    timeline: str,
    prizes: Optional[List[str]],
    sponsored_by: Optional[List[str]],
    min_team_size: int,
    max_team_size: int,
    start_date: datetime,
    end_date: datetime,
) -> str:
    prompt = f"""
You are helping generate content for a student hackathon page.

Based on the following information, create a compelling, informal description of the hackathon (max 4 sentences).
Include a short, motivational line at the end that encourages students to participate.

Hackathon Details:
- Name: {name}
- Theme: {theme}
- Mode: {mode}
- Start Date: {start_date.strftime("%Y-%m-%d")}
- End Date: {end_date.strftime("%Y-%m-%d")}
- Location: {location}
- Eligibility: {eligibility_criteria}
- Prizes: {", ".join(prizes or [])}
- Sponsors: {", ".join(sponsored_by or [])}
"""

    try:
        response = await ollama_async_client.chat(
            model=settings.OLLAMA_MODEL, messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM generation failed: {str(e)}")

    content = response.get("message", {}).get("content", "")
    if not content:
        raise HTTPException(status_code=500, detail="AI response missing content.")

    cleaned = clean_ai_description(content)

    return cleaned


async def create_hackathon(
    db: AsyncSession,
    user_id: UUID,
    name: str,
    start_date: datetime,
    end_date: datetime,
    registration_deadline: datetime,
    mode: str,
    theme: str,
    eligibility_criteria: str,
    min_team_size: int,
    max_team_size: int,
    submission_guidelines: str,
    rules: list,
    timeline: str,
    image: UploadFile,
    location: str,
    featured: Optional[bool] = False,
    prizes: Optional[List[str]] = None,
    sponsoredBy: Optional[List[str]] = None,
) -> HackathonInResponse:
    image_folder = settings.HACKATHON_IMAGE_PATH
    os.makedirs(image_folder, exist_ok=True)
    image_extension = image.filename.split(".")[-1]
    image_filename = f"{uuid4()}.{image_extension}"
    image_path = os.path.join(image_folder, image_filename)

    with open(image_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)

    # Generate description using AI
    description = await generate_hackathon_description_with_ai(
        name=name,
        theme=theme,
        mode=mode,
        location=location,
        eligibility_criteria=eligibility_criteria,
        rules=rules,
        timeline=timeline,
        prizes=prizes,
        sponsored_by=sponsoredBy,
        min_team_size=min_team_size,
        max_team_size=max_team_size,
        start_date=start_date,
        end_date=end_date,
    )

    hackathon = Hackathon(
        user_id=user_id,
        name=name,
        description=description,
        start_date=start_date,
        end_date=end_date,
        registration_deadline=registration_deadline,
        mode=mode,
        theme=theme,
        eligibility_criteria=eligibility_criteria,
        min_team_size=min_team_size,
        max_team_size=max_team_size,
        submission_guidelines=submission_guidelines,
        rules=sanitize_rules(rules),
        timeline=timeline,
        image=image_path,
        location=location,
        featured=featured,
        prizes=prizes,
        sponsoredBy=sponsoredBy,
    )

    db.add(hackathon)
    await db.commit()
    await db.refresh(hackathon)

    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()

    if user:
        template = TEMPLATES["hackathon_created"]
        subject = template["subject"].format(
            full_name=user.full_name, hackathon_name=hackathon.name
        )
        body = template["body"].format(
            full_name=user.full_name,
            hackathon_name=hackathon.name,
            start_date=start_date.strftime("%Y-%m-%d %H:%M"),
            end_date=end_date.strftime("%Y-%m-%d %H:%M"),
            registration_deadline=registration_deadline.strftime("%Y-%m-%d %H:%M"),
            mode=mode,
            theme=theme,
        )
        try:
            await send_email(
                settings.SENDER_EMAIL,
                settings.APP_PASSWORD,
                [user.email],
                subject,
                body,
            )
        except Exception as e:
            logger.error(f"Email not sent: {e}")

    return HackathonInResponse.from_orm(hackathon)


async def get_hackathons(db: AsyncSession):
    """
    Retrieve all hackathons from the database.

    Args:
        db (AsyncSession): SQLAlchemy async session.

    Returns:
        List[Hackathon]: A list of all hackathon objects.
    """
    result = await db.execute(select(Hackathon))
    hackathons = result.scalars().all()
    return hackathons


async def get_hackathon_image_file(hackathon_id: UUID, db: AsyncSession):
    """
    Serve the stored image file associated with a specific hackathon.

    Args:
        hackathon_id (UUID): ID of the hackathon.
        db (AsyncSession): SQLAlchemy async session.

    Returns:
        FileResponse: The image file if found.

    Raises:
        HTTPException: If the hackathon or image is not found or file doesn't exist.
    """
    result = await db.execute(select(Hackathon).filter_by(id=hackathon_id))
    hackathon = result.scalar_one_or_none()

    if not hackathon or not hackathon.image:
        raise HTTPException(status_code=404, detail="Hackathon or image not found")

    image_path = hackathon.image

    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    ext = os.path.splitext(image_path)[-1].lower()
    mime_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(ext, "application/octet-stream")

    return FileResponse(path=image_path, media_type=mime_type)


async def get_hackathon_by_id(
    db: AsyncSession, hackathon_id: UUID
) -> HackathonInResponse:
    """
    Retrieve a single hackathon by its ID.

    Args:
        db (AsyncSession): SQLAlchemy async session.
        hackathon_id (UUID): ID of the hackathon.

    Returns:
        HackathonInResponse: The requested hackathon.

    Raises:
        NotFoundException: If the hackathon is not found.
    """
    result = await db.execute(select(Hackathon).filter(Hackathon.id == hackathon_id))
    hackathon = result.scalar_one_or_none()
    if not hackathon:
        raise NotFoundException("Hackathon not found.")
    return HackathonInResponse.from_orm(hackathon)


async def get_hackathons_by_user_with_registration_counts(
    db: AsyncSession, user_id: UUID
):
    """
    Get all hackathons created by a specific user, along with team registration counts.

    Args:
        db (AsyncSession): SQLAlchemy async session.
        user_id (UUID): The ID of the hackathon creator.

    Returns:
        List[dict]: List of dictionaries containing hackathon details and registration counts.
    """
    result = await db.execute(select(Hackathon).filter(Hackathon.user_id == user_id))
    hackathons = result.scalars().all()

    results = []
    for hackathon in hackathons:
        reg_result = await db.execute(
            select(func.count(HackathonRegistration.id)).filter(
                HackathonRegistration.hackathon_id == hackathon.id
            )
        )
        registration_count = reg_result.scalar()
        results.append(
            {
                "hackathon": HackathonInResponse.from_orm(hackathon),
                "team_count": registration_count,
            }
        )

    return results


async def get_hackathon_count_by_user(db: AsyncSession, user_id: UUID) -> int:
    """
    Count the total number of hackathons created by a specific user.

    Args:
        db (AsyncSession): SQLAlchemy async session.
        user_id (UUID): ID of the user.

    Returns:
        int: Total number of hackathons.
    """
    result = await db.execute(
        select(func.count(Hackathon.id)).filter(Hackathon.user_id == user_id)
    )
    return result.scalar()


async def get_filtered_hackathons(
    db: AsyncSession,
    status: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[HackathonInResponse]:
    """
    Retrieve hackathons filtered by optional status and/or date range.

    Status can be one of:
        - "upcoming": Before registration deadline
        - "active": Ongoing between start and end dates
        - "completed": After end date

    Args:
        db (AsyncSession): SQLAlchemy async session.
        status (Optional[str]): Filter hackathons by status.
        start_date (Optional[datetime]): Start of date range filter.
        end_date (Optional[datetime]): End of date range filter.

    Returns:
        List[HackathonInResponse]: Filtered hackathon objects.

    Raises:
        HTTPException: If an invalid status filter is provided.
    """
    valid_statuses = {"upcoming", "active", "completed"}
    now = datetime.now(timezone.utc)

    # Base query with optional date range filtering
    stmt = select(Hackathon)
    if start_date and end_date:
        stmt = stmt.where(
            Hackathon.start_date >= start_date, Hackathon.end_date <= end_date
        )

    result = await db.execute(stmt)
    hackathons = result.scalars().all()

    filtered = []

    for hackathon in hackathons:
        # Determine status of the hackathon
        start = hackathon.start_date.replace(tzinfo=timezone.utc)
        end = hackathon.end_date.replace(tzinfo=timezone.utc)
        reg_deadline = hackathon.registration_deadline.replace(tzinfo=timezone.utc)

        if now < reg_deadline:
            current_status = "upcoming"
        elif start <= now <= end:
            current_status = "active"
        elif now > end:
            current_status = "completed"
        else:
            current_status = "upcoming"  # fallback

        # Filter based on requested status (if provided)
        if status:
            status = status.lower()
            if status not in valid_statuses:
                raise HTTPException(status_code=400, detail="Invalid status filter")
            if current_status != status:
                continue

        filtered.append(HackathonInResponse.from_orm(hackathon))

    return filtered


# -----------------problem statements-----------------------------


async def create_problem_statements(
    db: AsyncSession,
    ps_data: Union[ProblemStatementCreate, List[ProblemStatementCreate]],
) -> Union[ProblemStatement, List[ProblemStatement]]:
    """
    Create one or multiple problem statements.

    Args:
        db (AsyncSession): The async database session.
        ps_data (Union[ProblemStatementCreate, List[ProblemStatementCreate]]):
            A single problem statement or a list of them.

    Returns:
        Union[ProblemStatement, List[ProblemStatement]]:
            The created problem statement(s).
    """
    if isinstance(ps_data, list):
        ps_objects = [ProblemStatement(**ps.dict()) for ps in ps_data]
        db.add_all(ps_objects)
        await db.commit()
        return ps_objects
    else:
        ps = ProblemStatement(**ps_data.dict())
        db.add(ps)
        await db.commit()
        await db.refresh(ps)
        return ps


async def get_problem_statements_by_hackathon(
    db: AsyncSession,
    hackathon_id: UUID,
    skip: int = 0,
    limit: int = 10,
    featured: Optional[bool] = None,
):
    """
    Retrieve problem statements for a given hackathon.

    Args:
        db (AsyncSession): The async database session.
        hackathon_id (UUID): The ID of the hackathon.
        skip (int): Number of records to skip (pagination).
        limit (int): Maximum number of records to return.
        featured (Optional[bool]): Filter by featured status if provided.

    Returns:
        List[ProblemStatement]: List of problem statements.
    """
    stmt = select(ProblemStatement).where(ProblemStatement.hackathon_id == hackathon_id)
    if featured is not None:
        stmt = stmt.where(ProblemStatement.featured == featured)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_problem_statement_by_id(db: AsyncSession, ps_id: UUID):
    """
    Retrieve a problem statement by its ID.

    Args:
        db (AsyncSession): The async database session.
        ps_id (UUID): ID of the problem statement.

    Returns:
        ProblemStatement: The matching problem statement.

    Raises:
        NotFoundException: If no problem statement is found for the given ID.
    """
    stmt = select(ProblemStatement).where(ProblemStatement.id == ps_id)
    result = await db.execute(stmt)
    ps = result.scalar_one_or_none()
    if not ps:
        raise NotFoundException("Problem Statement not found for this id.")
    return ps


async def update_problem_statement(
    db: AsyncSession, ps_id: UUID, update_data: ProblemStatementUpdate
):
    """
    Update a problem statement by its ID.

    Args:
        db (AsyncSession): The async database session.
        ps_id (UUID): ID of the problem statement to update.
        update_data (ProblemStatementUpdate): The fields to update.

    Returns:
        ProblemStatement: The updated problem statement.

    Raises:
        NotFoundException: If no problem statement is found for the given ID.
    """
    stmt = select(ProblemStatement).where(ProblemStatement.id == ps_id)
    result = await db.execute(stmt)
    ps = result.scalar_one_or_none()
    if not ps:
        raise NotFoundException("Problem Statement not found.")
    for key, value in update_data.dict(exclude_unset=True).items():
        setattr(ps, key, value)
    await db.commit()
    await db.refresh(ps)
    return ps


async def delete_problem_statement(db: AsyncSession, ps_id: UUID):
    """
    Delete a problem statement by its ID.

    Args:
        db (AsyncSession): The async database session.
        ps_id (UUID): ID of the problem statement to delete.

    Returns:
        str: Success message.

    Raises:
        NotFoundException: If no problem statement is found for the given ID.
    """
    stmt = select(ProblemStatement).where(ProblemStatement.id == ps_id)
    result = await db.execute(stmt)
    ps = result.scalar_one_or_none()
    if not ps:
        raise NotFoundException("Problem Statement not found.")
    await db.delete(ps)
    await db.commit()
    return f"Problem Statement {ps_id} deleted successfully"


# ---------------------registrations-----------------------


async def create_team_and_register(
    db: AsyncSession, data: TeamWithRegistrationCreate
) -> HackathonRegistration:
    """
    Create a new team, add its members, and register the team for a specific hackathon.

    This function:
      - Creates a new team with the provided name.
      - Adds multiple students to the team.
      - Registers the team to a specified hackathon with eligibility agreement.

    Args:
        db (AsyncSession): The async SQLAlchemy session.
        data (TeamWithRegistrationCreate): Payload containing team details and registration data.

    Returns:
        HackathonRegistration: The created hackathon registration record.
    """
    team = Team(team_name=data.team_name)
    db.add(team)
    await db.flush()

    team_members = [
        TeamStudent(team_id=team.team_id, student_id=student_id)
        for student_id in data.members
    ]
    db.add_all(team_members)

    # Register to hackathon
    registration = HackathonRegistration(
        team_id=team.team_id,
        hackathon_id=data.hackathon_id,
        agreed_to_eligibility=data.agreed_to_eligibility,
    )
    db.add(registration)

    await db.commit()
    await db.refresh(registration)
    await db.refresh(team)

    return registration


async def get_registrations_by_hackathon(
    db: AsyncSession, hackathon_id: UUID
) -> list[HackathonRegistration]:
    """
    Retrieve all team registrations for a given hackathon.

    Args:
        db (AsyncSession): The async SQLAlchemy session.
        hackathon_id (UUID): UUID of the hackathon.

    Returns:
        list[HackathonRegistration]: List of registrations with team details preloaded.
    """
    result = await db.execute(
        select(HackathonRegistration)
        .options(selectinload(HackathonRegistration.team))  # This loads team eagerly
        .filter_by(hackathon_id=hackathon_id)
    )
    return result.scalars().all()


async def get_team(db: AsyncSession, team_id: UUID) -> Team | None:
    """
    Fetch a single team along with its members and hackathon registrations.

    Args:
        db (AsyncSession): The async SQLAlchemy database session.
        team_id (UUID): The ID of the team to retrieve.

    Returns:
        Team | None: The team object with relationships loaded, or None if not found.
    """
    result = await db.execute(
        select(Team)
        .options(
            selectinload(Team.members),
            selectinload(Team.registrations).selectinload(HackathonRegistration.team),
        )
        .filter_by(team_id=team_id)
    )
    return result.scalar_one_or_none()


async def get_all_teams(db: AsyncSession) -> list[Team]:
    """
    Retrieve all teams from the database, including their members and registrations.

    Args:
        db (AsyncSession): The async SQLAlchemy session.

    Returns:
        list[Team]: A list of all teams with related data eagerly loaded.
    """
    result = await db.execute(
        select(Team).options(
            selectinload(Team.members),
            selectinload(Team.registrations).selectinload(HackathonRegistration.team),
        )
    )
    return result.scalars().all()


async def get_team_students(db: AsyncSession, team_id: UUID):
    """
    Retrieve all students in a given team along with their associated user profiles.

    Args:
        db (AsyncSession): The async SQLAlchemy session.
        team_id (UUID): The UUID of the team.

    Returns:
        List[Tuple[TeamStudent, Student, User]]: A list of tuples, each containing:
            - TeamStudent relation
            - Student entity
            - Corresponding User profile
    """
    stmt = (
        select(TeamStudent, Student, User)
        .join(Student, TeamStudent.student_id == Student.student_id)
        .join(User, Student.user_id == User.user_id)
        .filter(TeamStudent.team_id == team_id)
    )
    result = await db.execute(stmt)
    return result.all()


async def get_team_registrations(db: AsyncSession, team_id: UUID):
    """
    Retrieve all hackathon registrations associated with a specific team.

    Args:
        db (AsyncSession): The async SQLAlchemy session.
        team_id (UUID): The UUID of the team.

    Returns:
        List[Tuple[HackathonRegistration, Team]]: A list of tuples containing:
            - Registration entry
            - Corresponding team
    """
    stmt = (
        select(HackathonRegistration, Team)
        .join(Team, HackathonRegistration.team_id == Team.team_id)
        .filter(HackathonRegistration.team_id == team_id)
    )
    result = await db.execute(stmt)
    return result.all()


async def add_students_to_team(
    db: AsyncSession, team_student_data: TeamStudentCreate
) -> List[TeamStudentResponse]:
    """
    Add multiple students to an existing team.

    Verifies if each student and their corresponding user profile exists before adding.
    Prevents duplicate entries using database constraints.

    Args:
        db (AsyncSession): The async SQLAlchemy session.
        team_student_data (TeamStudentCreate): Contains team ID and list of student IDs.

    Returns:
        List[TeamStudentResponse]: Successfully added students with full names.

    Raises:
        HTTPException: If a student or their user profile is not found,
                       or if the student is already in the team.
    """
    responses = []

    for student_id in team_student_data.student_ids:
        result = await db.execute(
            select(Student)
            .options(selectinload(Student.user))
            .where(Student.student_id == student_id)
        )
        student = result.scalar_one_or_none()

        if not student:
            raise HTTPException(
                status_code=404, detail=f"Student {student_id} not found"
            )

        if not student.user:
            raise HTTPException(
                status_code=404, detail=f"User for student {student_id} not found"
            )

        full_name = student.user.full_name

        team_student = TeamStudent(
            team_id=team_student_data.team_id, student_id=student.student_id
        )

        db.add(team_student)

        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=400,
                detail=f"Student {student_id} already added to this team",
            )

        responses.append(
            TeamStudentResponse(
                team_id=team_student.team_id,
                student_id=student.student_id,
                student_name=full_name,
            )
        )

    return responses


async def get_hackathon_status_by_id(hackathon_id: UUID, db: AsyncSession) -> dict:
    """
    Determine the current status of a hackathon based on time-related fields.

    Status logic:
      - "Upcoming": If current time is before the registration deadline.
      - "Active": If current time is between start and end times.
      - "Ended": If current time is after the end time.

    Args:
        hackathon_id (UUID): The unique ID of the hackathon.
        db (AsyncSession): The async SQLAlchemy session.

    Returns:
        dict: Dictionary with `hackathon_id` and the current `status`.

    Raises:
        HTTPException: If the hackathon is not found.
    """
    result = await db.execute(select(Hackathon).filter(Hackathon.id == hackathon_id))
    hackathon = result.scalar_one_or_none()

    if not hackathon:
        raise HTTPException(status_code=404, detail="Hackathon not found")

    now = datetime.now(timezone.utc)
    start = hackathon.start_date.replace(tzinfo=timezone.utc)
    end = hackathon.end_date.replace(tzinfo=timezone.utc)
    reg_deadline = hackathon.registration_deadline.replace(tzinfo=timezone.utc)

    if now < reg_deadline:
        status = "Upcoming"
    elif start <= now <= end:
        status = "Active"
    elif now > end:
        status = "Ended"
    else:
        status = "Upcoming"  # Fallback

    return {"hackathon_id": str(hackathon.id), "status": status}


# -------------submissions--------------------------


async def process_submission(
    submission_type: Optional[str] = None,
    file: Optional[UploadFile] = None,
    bucket_name: Optional[str] = None,
    submission_id: UUID = None,
    url: Optional[str] = None,
    github_url: Optional[str] = None,
) -> str:
    """
    Process a submission based on the specified type.

    Depending on `submission_type`, it:
    - Uploads a ZIP file locally or to S3.
    - Stores a regular URL.
    - Stores a GitHub URL.

    Args:
        submission_type (str): Type of the submission ("zip", "url", or "github").
        file (UploadFile, optional): ZIP file to upload.
        bucket_name (str, optional): Name of the S3 bucket for file storage.
        submission_id (UUID): Unique identifier for the submission.
        url (str, optional): URL submission value.
        github_url (str, optional): GitHub URL submission value.

    Returns:
        str: File path or URL of the processed submission.

    Raises:
        HTTPException: If required fields are missing or submission type is invalid.
    """
    if submission_type == "zip":
        if not file:
            raise HTTPException(
                status_code=400, detail="File is required for zip submission."
            )
        return await handle_zip_submission(file, submission_id, bucket_name)
    elif submission_type == "url":
        if not url:
            raise HTTPException(
                status_code=400, detail="URL is required for URL submission."
            )
        return handle_url_submission(url, submission_id)
    elif submission_type == "github":
        if not github_url:
            raise HTTPException(
                status_code=400, detail="GitHub URL is required for GitHub submission."
            )
        return handle_github_submission(github_url, submission_id)
    else:
        raise HTTPException(status_code=400, detail="Invalid submission type.")


async def handle_zip_submission(
    file: UploadFile, submission_id: UUID, bucket_name: str = None
) -> str:
    """
    Handle and store ZIP file submissions.

    Stores the file either locally or on S3 depending on presence of `bucket_name`.

    Args:
        file (UploadFile): The ZIP file to be saved.
        submission_id (UUID): Unique ID of the submission.
        bucket_name (str, optional): If provided, uploads file to the specified S3 bucket.

    Returns:
        str: Path or URL to the uploaded ZIP file.
    """
    if bucket_name:
        return await upload_file_to_s3(file, submission_id, bucket_name)
    else:
        return await save_file_locally(file, submission_id)


def handle_url_submission(url: str, submission_id: UUID) -> str:
    """
    Handle standard URL submissions.

    Args:
        url (str): The submitted URL.
        submission_id (UUID): Submission ID for tracking.

    Returns:
        str: The URL (unchanged).
    """
    return url


def handle_github_submission(github_url: str, submission_id: UUID) -> str:
    """
    Handle GitHub URL submissions.

    Args:
        github_url (str): Submitted GitHub URL.
        submission_id (UUID): Submission ID for tracking.

    Returns:
        str: The GitHub URL (unchanged).
    """
    return github_url


async def get_submissions_by_hackathon_and_problem(
    db: AsyncSession, hackathon_id: UUID, problem_statement_id: UUID
):
    """
    Retrieve all submissions for a specific hackathon and problem statement.

    Args:
        db (AsyncSession): Async SQLAlchemy session.
        hackathon_id (UUID): ID of the hackathon.
        problem_statement_id (UUID): ID of the problem statement.

    Returns:
        List[Submission]: List of matching submissions.
    """
    stmt = select(Submission).filter(
        Submission.hackathon_id == hackathon_id,
        Submission.problem_statement_id == problem_statement_id,
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_submission_file_path(submission_id: UUID, db: AsyncSession) -> str:
    """
    Get the file path of a submitted ZIP file based on submission ID.

    Args:
        submission_id (UUID): Unique ID of the submission.
        db (AsyncSession): Async SQLAlchemy session.

    Returns:
        str: File path of the ZIP submission.

    Raises:
        HTTPException: If the submission or file is not found.
    """
    stmt = select(Submission).filter(Submission.id == submission_id)
    result = await db.execute(stmt)
    submission = result.scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    file_path = os.path.join("uploads", "submissions", f"{submission_id}.zip")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    return file_path


async def count_submissions_for_hackathon(db: AsyncSession, hackathon_id: str) -> int:
    """
    Count the total number of submissions made for a given hackathon.

    Args:
        db (AsyncSession): Async SQLAlchemy session.
        hackathon_id (str): ID of the hackathon.

    Returns:
        int: Number of submissions for the hackathon.
    """
    stmt = (
        select(func.count())
        .select_from(Submission)
        .filter(Submission.hackathon_id == hackathon_id)
    )
    result = await db.execute(stmt)
    return result.scalar()


# -----------scoring--------------------------------------


async def create_score(db: AsyncSession, scoring_data: ScoringCreate) -> Scoring:
    """
    Create a new score record associated with a submission and hackathon.

    Args:
        db (AsyncSession): Async SQLAlchemy session.
        scoring_data (ScoringCreate): Payload containing score and related references.

    Returns:
        Scoring: The newly created scoring record.
    """
    scoring = Scoring(**scoring_data.dict())
    db.add(scoring)
    await db.commit()
    await db.refresh(scoring)
    return scoring


async def update_score(
    db: AsyncSession, scoring_id: UUID, score_update: ScoringUpdate
) -> Scoring | None:
    """
    Update the score value of an existing scoring record.

    Args:
        db (AsyncSession): Async SQLAlchemy session.
        scoring_id (UUID): ID of the scoring record to update.
        score_update (ScoringUpdate): New score value.

    Returns:
        Scoring | None: Updated scoring record, or None if not found.
    """
    result = await db.execute(select(Scoring).filter(Scoring.id == scoring_id))
    scoring = result.scalar_one_or_none()

    if not scoring:
        return None

    scoring.score = score_update.score
    await db.commit()
    await db.refresh(scoring)
    return scoring


async def get_score_by_submission(
    db: AsyncSession, submission_id: UUID
) -> Scoring | None:
    """
    Retrieve the score record associated with a specific submission.

    Args:
        db (AsyncSession): Async SQLAlchemy session.
        submission_id (UUID): ID of the submission.

    Returns:
        Scoring | None: The score record if found, otherwise None.
    """
    result = await db.execute(
        select(Scoring).filter(Scoring.submission_id == submission_id)
    )
    return result.scalar_one_or_none()


async def get_scores_by_hackathon(
    db: AsyncSession, hackathon_id: UUID
) -> list[Scoring]:
    """
    Retrieve all scoring records for a specific hackathon.

    Args:
        db (AsyncSession): Async SQLAlchemy session.
        hackathon_id (UUID): ID of the hackathon.

    Returns:
        list[Scoring]: List of scoring records.
    """
    result = await db.execute(
        select(Scoring).filter(Scoring.hackathon_id == hackathon_id)
    )
    return result.scalars().all()


# ------------------------generate---------------------------------


async def generate_hackathon_from_job(job_id: UUID, db: AsyncSession) -> dict:
    """
    Asynchronously generate a creative hackathon theme and description from a job posting
    using Ollama's LLM.

    Args:
        job_id (UUID): The UUID of the job posting.
        db (AsyncSession): Async SQLAlchemy session.

    Returns:
        dict: Dictionary containing the generated 'theme' and 'description'.
    """
    # Fetch job posting
    result = await db.execute(select(JobPosting).where(JobPosting.job_id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.description:
        raise HTTPException(status_code=400, detail="Job description is empty")

    # Construct LLM prompt
    prompt = (
        f"Generate a creative and engaging hackathon theme and description "
        f"based on the following job description:\n\n{job.description}\n\n"
        f"Respond in the following format:\n"
        f"Theme: <theme>\nDescription: <description>"
    )

    try:
        response = await ollama_async_client.chat(
            model=settings.OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"top_p": 0.7, "temperature": 0.4, "max_tokens": 2000},
        )
        generated_text = response["message"]["content"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ollama API error: {str(e)}")

    if not generated_text:
        raise HTTPException(status_code=500, detail="No content returned from model")

    # Parse output
    theme = description = None
    for line in generated_text.splitlines():
        if line.lower().startswith("theme:"):
            theme = line.split(":", 1)[1].strip()
        elif line.lower().startswith("description:"):
            description = line.split(":", 1)[1].strip()

    if not theme or not description:
        raise HTTPException(
            status_code=500, detail="Generated text could not be parsed correctly"
        )

    return {"theme": theme, "description": description}
