from fastapi import (
    APIRouter,
    Depends,
    status,
    UploadFile,
    File,
    Form,
    Path,
    HTTPException,
)

from app.database.models.hackathon_models import Team, Submission
from app.schemas.hackathon_schemas import (
    HackathonInResponse,
    TeamWithRegistrationCreate,
    HackathonRegistrationResponse,
    ProblemStatementCreate,
    ProblemStatementInResponse,
    ProblemStatementUpdate,
    TeamResponse,
    TeamStudentResponse,
    TeamStudentCreate,
    SubmissionOut,
    ScoringUpdate,
    ScoringCreate,
    ScoringOut,
)

from app.services.hackathon_services import (
    add_students_to_team,
    create_hackathon,
    delete_problem_statement,
    create_problem_statements,
    get_all_teams,
    get_hackathon_by_id,
    get_hackathon_count_by_user,
    get_hackathon_status_by_id,
    get_hackathons,
    get_hackathons_by_user_with_registration_counts,
    get_problem_statement_by_id,
    get_problem_statements_by_hackathon,
    get_registrations_by_hackathon,
    get_team,
    get_team_registrations,
    get_team_students,
    update_problem_statement,
    get_hackathon_image_file,
    get_submission_file_path,
    count_submissions_for_hackathon,
    get_submissions_by_hackathon_and_problem,
    create_score,
    update_score,
    get_score_by_submission,
    get_scores_by_hackathon,
    get_filtered_hackathons,
    create_team_and_register,
    generate_hackathon_from_job,
)
from app.database.db import get_db
from typing import List, Optional, Union
from uuid import UUID
from datetime import datetime


from fastapi.responses import FileResponse
from app.utils.file_storage import (
    save_file_locally,
    is_duplicate_submission,
    upload_file_to_s3,
)
from uuid import uuid4

from app.database.models.hackathon_models import (
    SubmissionType,
)
from sqlalchemy.ext.asyncio import AsyncSession


# ---------- Hackathon Routes ------------------
router = APIRouter(prefix="/api/hackathon", tags=["Hackathon"])


@router.post(
    "/admin/create",
    response_model=HackathonInResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_new_hackathon(
    name: str = Form(...),
    start_date: datetime = Form(...),
    end_date: datetime = Form(...),
    registration_deadline: datetime = Form(...),
    mode: str = Form(...),
    theme: str = Form(...),
    eligibility_criteria: str = Form(...),
    min_team_size: int = Form(...),
    max_team_size: int = Form(...),
    submission_guidelines: str = Form(...),
    rules: str = Form(...),
    timeline: str = Form(...),
    image: UploadFile = File(...),
    location: str = Form(...),
    prizes: str = Form(...),
    sponsoredBy: str = Form(...),
    featured: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Form(...),
):
    """
    Create a new hackathon (Admin only).

    Automatically generates an inspiring hackathon description and motivational line using AI
    based on the provided fields like name, theme, mode, and timeline. Supports file uploads,
    and accepts comma-separated values for rules, prizes, and sponsors.

    Returns:
        HackathonInResponse: The newly created hackathon details.
    """
    return await create_hackathon(
        db=db,
        user_id=user_id,
        name=name,
        start_date=start_date,
        end_date=end_date,
        registration_deadline=registration_deadline,
        mode=mode,
        theme=theme,
        eligibility_criteria=eligibility_criteria,
        min_team_size=min_team_size,
        max_team_size=max_team_size,
        submission_guidelines=submission_guidelines,
        rules=[rule.strip() for rule in rules.split(",") if rule.strip()],
        timeline=timeline,
        image=image,
        location=location,
        prizes=[p.strip() for p in prizes.split(",") if p.strip()],
        sponsoredBy=[s.strip() for s in sponsoredBy.split(",") if s.strip()],
        featured=featured,
    )


@router.get("/admin/list", response_model=List[HackathonInResponse])
async def list_all_hackathons(db: AsyncSession = Depends(get_db)):
    """
    Retrieve a list of all hackathons (Admin only).

    This endpoint returns a list of all hackathons in the system. It is intended for
    administrative overviews.

    Returns:
        List[HackathonInResponse]: List of all hackathons.
    """
    return await get_hackathons(db=db)


@router.get("/admin/{hackathon_id}", response_model=HackathonInResponse)
async def get_single_hackathon(hackathon_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Get details of a specific hackathon (Admin only).

    Fetches the full details of a hackathon by its unique ID.

    Args:
        hackathon_id (UUID): The ID of the hackathon.

    Returns:
        HackathonInResponse: The detailed hackathon data.
    """
    return await get_hackathon_by_id(db=db, hackathon_id=hackathon_id)


@router.get("/hackathons/by-user/{user_id}")
async def list_user_hackathons_with_team_counts(
    user_id: UUID, db: AsyncSession = Depends(get_db)
):
    """
    List all hackathons created by a specific user along with team registration counts.

    Args:
        user_id (UUID): ID of the user whose hackathons are to be retrieved.

    Returns:
        List[dict]: Hackathon data with team registration count included.
    """
    return await get_hackathons_by_user_with_registration_counts(db, user_id)


@router.get("/user/{user_id}/hackathon-count")
async def hackathon_count(user_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Get the total number of hackathons created by a specific user.

    Args:
        user_id (UUID): The user’s unique identifier.

    Returns:
        dict: Object containing user ID and number of hackathons created.
    """
    count = await get_hackathon_count_by_user(db, user_id)
    return {"user_id": user_id, "hackathon_count": count}


@router.get("/{hackathon_id}/image")
async def fetch_hackathon_image(hackathon_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Fetch the image file associated with a specific hackathon.

    Args:
        hackathon_id (UUID): ID of the hackathon.

    Returns:
        StreamingResponse/FileResponse: The image file for the hackathon.
    """
    return await get_hackathon_image_file(hackathon_id, db)


@router.get("/hackathons/filter", response_model=List[HackathonInResponse])
async def filter_hackathons(
    status: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Filter hackathons based on status and/or date range.

    Args:
        status (str, optional): Current status (e.g., upcoming, ongoing, completed).
        start_date (datetime, optional): Filter hackathons starting after this date.
        end_date (datetime, optional): Filter hackathons ending before this date.

    Returns:
        List[HackathonInResponse]: Filtered list of hackathons.
    """
    return await get_filtered_hackathons(db, status, start_date, end_date)


# ---------------problem statments----------------------------------


@router.post(
    "/problem-statements/",
    response_model=Union[ProblemStatementInResponse, List[ProblemStatementInResponse]],
)
async def create_problem_statements_route(
    problem_statements: Union[ProblemStatementCreate, List[ProblemStatementCreate]],
    db: AsyncSession = Depends(get_db),
):
    """
    Create one or more problem statements for a hackathon.

    Accepts either a single problem statement or a list of them, and associates them
    with the appropriate hackathon.

    Returns:
        ProblemStatementInResponse or List[ProblemStatementInResponse]: The created problem statements.
    """
    return await create_problem_statements(db, problem_statements)


@router.get(
    "/problem-statements/hackathon/{hackathon_id}",
    response_model=List[ProblemStatementInResponse],
)
async def get_by_hackathon(
    hackathon_id: UUID,
    skip: int = 0,
    limit: int = 10,
    featured: bool = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Get all problem statements for a given hackathon.

    Optionally filters results based on the `featured` flag.

    Args:
        hackathon_id (UUID): Hackathon to which the problems belong.
        skip (int): Pagination skip.
        limit (int): Pagination limit.
        featured (bool, optional): If True, return only featured problem statements.

    Returns:
        List[ProblemStatementInResponse]: List of problem statements.
    """
    return await get_problem_statements_by_hackathon(
        db, hackathon_id, skip, limit, featured
    )


@router.get(
    "/problem-statements/{problem_statement_id}",
    response_model=ProblemStatementInResponse,
)
async def get(problem_statement_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Retrieve a specific problem statement by its ID.

    Args:
        problem_statement_id (UUID): The ID of the problem statement.

    Returns:
        ProblemStatementInResponse: The requested problem statement.
    """
    return await get_problem_statement_by_id(db, problem_statement_id)


@router.put(
    "/problem-statements/{problem_statement_id}",
    response_model=ProblemStatementInResponse,
)
async def update(
    problem_statement_id: UUID,
    problem_statement_update: ProblemStatementUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Update an existing problem statement.

    Allows modification of fields such as title, description, difficulty, etc.

    Args:
        problem_statement_id (UUID): The ID of the problem statement to update.
        problem_statement_update (ProblemStatementUpdate): The new data.

    Returns:
        ProblemStatementInResponse: The updated problem statement.
    """
    return await update_problem_statement(
        db, problem_statement_id, problem_statement_update
    )


@router.delete("/problem-statements/{problem_statement_id}", response_model=str)
async def delete(problem_statement_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Delete a problem statement.

    Permanently removes the problem statement from the database.

    Args:
        problem_statement_id (UUID): The ID of the problem statement.

    Returns:
        str: Confirmation message.
    """
    return await delete_problem_statement(db, problem_statement_id)


# -----------------registrations and create team-------------------------
@router.post(
    "/register-team",
    response_model=HackathonRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_team_and_register_route(
    data: TeamWithRegistrationCreate, db: AsyncSession = Depends(get_db)
):
    """
    Register a new team for a hackathon.

    This endpoint creates a new team and registers it for a specific hackathon
    in one transaction. It validates the registration data, stores the team info,
    and returns a confirmation response.

    Args:
        data (TeamWithRegistrationCreate): Payload with team and hackathon registration details.

    Returns:
        HackathonRegistrationResponse: A success message with team and hackathon details.
    """
    registration = await create_team_and_register(db, data)

    # Eager load team to avoid MissingGreenlet
    team = await db.get(Team, registration.team_id)

    return HackathonRegistrationResponse(
        message="Team created and registered successfully",
        team_id=registration.team_id,
        team_name=team.team_name if team else "Unknown",
        hackathon_id=registration.hackathon_id,
        agreed_to_eligibility=registration.agreed_to_eligibility,
    )


@router.get(
    "/registrations/{hackathon_id}",
    response_model=List[HackathonRegistrationResponse],
)
async def get_registrations_for_hackathon(
    hackathon_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get all registrations for a specific hackathon.

    This endpoint returns a list of teams registered for the given hackathon.

    Args:
        hackathon_id (UUID): The ID of the hackathon.

    Returns:
        List[HackathonRegistrationResponse]: List of team registrations.
    """
    registrations = await get_registrations_by_hackathon(db, hackathon_id)

    return [
        HackathonRegistrationResponse(
            message="Successfully fetched registration",
            team_id=reg.team_id,
            team_name=reg.team.team_name if reg.team else "Unknown",
            hackathon_id=reg.hackathon_id,
            agreed_to_eligibility=reg.agreed_to_eligibility,
        )
        for reg in registrations
    ]


@router.get("/registeredteamslist", response_model=List[TeamResponse])
async def list_teams(db: AsyncSession = Depends(get_db)):
    """
    Retrieve all registered teams.

    Returns all teams along with their members and associated hackathon registrations.

    Returns:
        List[TeamResponse]: A list of team responses including student IDs and registration details.
    """
    teams = await get_all_teams(db)

    return [
        TeamResponse(
            team_id=team.team_id,
            team_name=team.team_name,
            created_at=team.created_at,
            members=[member.student_id for member in team.members],
            registrations=[
                HackathonRegistrationResponse(
                    message="teams registered retrieved",
                    id=reg.id,
                    team_id=reg.team_id,
                    team_name=reg.team.team_name,
                    hackathon_id=reg.hackathon_id,
                    agreed_to_eligibility=reg.agreed_to_eligibility,
                )
                for reg in team.registrations
            ],
        )
        for team in teams
    ]


@router.get("/team/{team_id}", response_model=TeamResponse)
async def get_team_by_id(team_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Get team details by team ID.

    Returns basic team details including team name, creation time,
    members, and hackathon registrations.

    Args:
        team_id (UUID): ID of the team.

    Returns:
        TeamResponse: Full details of the team.
    """
    team = await get_team(db, team_id)

    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    return TeamResponse(
        team_id=team.team_id,
        team_name=team.team_name,
        created_at=team.created_at,
        members=[member.student_id for member in team.members],
        registrations=[
            HackathonRegistrationResponse(
                message="team registration retrieved",
                id=reg.id,
                team_id=reg.team_id,
                team_name=reg.team.team_name,
                hackathon_id=reg.hackathon_id,
                agreed_to_eligibility=reg.agreed_to_eligibility,
            )
            for reg in team.registrations
        ],
    )


@router.get("/{team_id}/details", response_model=TeamResponse)
async def get_team_with_students(team_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Get detailed team information including student info.

    Retrieves a team along with its members and registration data.
    Useful for viewing enriched team info with student names.

    Args:
        team_id (UUID): The team ID.

    Returns:
        TeamResponse: The team data with detailed student/member info.
    """
    team = await get_team(db, team_id)
    registrations = await get_team_registrations(db, team_id)

    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    return TeamResponse(
        team_id=team.team_id,
        team_name=team.team_name,
        created_at=team.created_at,
        members=[member.student_id for member in team.members],
        registrations=[
            HackathonRegistrationResponse(
                message="Registration retrieved",
                team_id=registration.team_id,
                team_name=team.team_name,
                hackathon_id=registration.hackathon_id,
                agreed_to_eligibility=registration.agreed_to_eligibility,
            )
            for registration, team in registrations
        ],
    )


@router.post("/add_students", response_model=List[TeamStudentResponse])
async def add_students(
    team_student_data: TeamStudentCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Add students to an existing team.

    Registers one or more students to a given team by student IDs.

    Args:
        team_student_data (TeamStudentCreate): Data including team ID and student IDs.

    Returns:
        List[TeamStudentResponse]: Confirmation of added students with team IDs.
    """
    return await add_students_to_team(db, team_student_data)


@router.get("/{team_id}/students", response_model=List[TeamStudentResponse])
async def list_team_students(team_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    List all students in a team.

    Returns:
        List[TeamStudentResponse]: A list of students in the given team with names.
    """
    team_students = await get_team_students(db, team_id)

    return [
        TeamStudentResponse(
            team_id=ts.team_id, student_id=ts.student_id, student_name=user.full_name
        )
        for ts, student, user in team_students
    ]


@router.get(
    "/{team_id}/registrations", response_model=List[HackathonRegistrationResponse]
)
async def list_team_registrations(team_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    List all hackathon registrations for a team.

    Args:
        team_id (UUID): ID of the team.

    Returns:
        List[HackathonRegistrationResponse]: Registrations the team has made to hackathons.
    """
    registrations = await get_team_registrations(db, team_id)

    return [
        HackathonRegistrationResponse(
            message=f"Team {team.team_name} registered successfully",
            team_id=reg.team_id,
            team_name=team.team_name,
            hackathon_id=reg.hackathon_id,
            agreed_to_eligibility=reg.agreed_to_eligibility,
        )
        for reg, team in registrations
    ]


@router.get("/hackathons/{hackathon_id}/status")
async def get_hackathon_status(
    hackathon_id: str = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the current status of a hackathon.

    Determines whether the hackathon is upcoming, ongoing, or completed.

    Args:
        hackathon_id (str): The ID of the hackathon.

    Returns:
        dict: Dictionary with hackathon ID and its current status.
    """
    return await get_hackathon_status_by_id(hackathon_id, db)


@router.post("/submissions/local")
async def submit_local(
    submission_type: SubmissionType = Form(...),
    file: Optional[UploadFile] = File(default=None),
    url: Optional[str] = Form(None),
    github_url: Optional[str] = Form(None),
    problem_statement_id: UUID = Form(...),
    hackathon_id: UUID = Form(...),
    team_id: UUID = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a solution locally for a problem statement in a hackathon.

    Supports submissions via ZIP file, GitHub URL, or general URL.
    The file will be stored locally on the server.

    Args:
        submission_type (SubmissionType): Type of the submission.
        file (UploadFile): ZIP file (required if type is ZIP).
        url (str): Link (required if type is URL).
        github_url (str): GitHub repo link (required if type is GITHUB).
        problem_statement_id (UUID): ID of the problem being solved.
        hackathon_id (UUID): ID of the associated hackathon.
        team_id (UUID): ID of the submitting team.

    Returns:
        dict: Submission ID and success message.
    """

    if await is_duplicate_submission(db, team_id, hackathon_id, problem_statement_id):
        raise HTTPException(
            status_code=400,
            detail="A submission already exists for this team, hackathon, and problem statement.",
        )

    submission_id = uuid4()

    try:
        # Handle submission logic
        if submission_type == SubmissionType.ZIP:
            if not file:
                raise HTTPException(
                    status_code=400, detail="File is required for ZIP submission."
                )

            saved_path = await save_file_locally(file, submission_id)
            submission = Submission(
                id=submission_id,
                submission_type=submission_type,
                filename=file.filename,
                filepath=saved_path,
                submission_value=saved_path,  # for convenience
                problem_statement_id=problem_statement_id,
                hackathon_id=hackathon_id,
                team_id=team_id,
            )

        elif submission_type == SubmissionType.URL:
            if not url:
                raise HTTPException(status_code=400, detail="URL is required.")
            submission = Submission(
                id=submission_id,
                submission_type=submission_type,
                submission_value=url,
                problem_statement_id=problem_statement_id,
                hackathon_id=hackathon_id,
                team_id=team_id,
            )

        elif submission_type == SubmissionType.GITHUB:
            if not github_url:
                raise HTTPException(status_code=400, detail="GitHub URL is required.")
            submission = Submission(
                id=submission_id,
                submission_type=submission_type,
                submission_value=github_url,
                problem_statement_id=problem_statement_id,
                hackathon_id=hackathon_id,
                team_id=team_id,
            )

        else:
            raise HTTPException(status_code=400, detail="Unsupported submission type.")

        db.add(submission)
        await db.commit()

        return {
            "submission_id": submission_id,
            "message": "Submission saved successfully.",
        }

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/submissions/s3")
async def submit_s3(
    submission_type: SubmissionType = Form(...),
    file: Optional[UploadFile] = File(default=None),
    url: Optional[str] = Form(None),
    github_url: Optional[str] = Form(None),
    problem_statement_id: UUID = Form(...),
    hackathon_id: UUID = Form(...),
    team_id: UUID = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a solution to S3 storage for a problem statement in a hackathon.

    Accepts ZIP file (uploaded to S3), GitHub URL, or general URL.

    Args:
        submission_type (SubmissionType): Type of submission.
        file (UploadFile): ZIP file for S3 (if applicable).
        url (str): Direct submission link.
        github_url (str): GitHub repository URL.
        problem_statement_id (UUID): ID of the problem being solved.
        hackathon_id (UUID): ID of the hackathon.
        team_id (UUID): ID of the submitting team.

    Returns:
        dict: Submission ID and confirmation message.
    """
    if await is_duplicate_submission(db, team_id, hackathon_id, problem_statement_id):
        raise HTTPException(
            status_code=400,
            detail="Submission already exists for this team, hackathon, and problem statement.",
        )

    submission_id = uuid4()

    try:
        if submission_type == SubmissionType.ZIP:
            if not file:
                raise HTTPException(
                    status_code=400, detail="File is required for ZIP submission."
                )

            # Upload to S3 and return S3 URL
            s3_url = await upload_file_to_s3(
                file, submission_id, bucket_name="your-bucket"
            )

            submission = Submission(
                id=submission_id,
                submission_type=submission_type,
                filename=file.filename,
                filepath=s3_url,
                submission_value=s3_url,
                problem_statement_id=problem_statement_id,
                hackathon_id=hackathon_id,
                team_id=team_id,
            )

        elif submission_type == SubmissionType.URL:
            if not url:
                raise HTTPException(status_code=400, detail="URL is required.")
            submission = Submission(
                id=submission_id,
                submission_type=submission_type,
                submission_value=url,
                problem_statement_id=problem_statement_id,
                hackathon_id=hackathon_id,
                team_id=team_id,
            )

        elif submission_type == SubmissionType.GITHUB:
            if not github_url:
                raise HTTPException(status_code=400, detail="GitHub URL is required.")
            submission = Submission(
                id=submission_id,
                submission_type=submission_type,
                submission_value=github_url,
                problem_statement_id=problem_statement_id,
                hackathon_id=hackathon_id,
                team_id=team_id,
            )

        else:
            raise HTTPException(status_code=400, detail="Unsupported submission type.")

        db.add(submission)
        await db.commit()

        return {
            "submission_id": submission_id,
            "message": "S3 submission saved successfully.",
        }

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/submission/{submission_id}/download")
async def download_submission(submission_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Download a submitted ZIP file for a specific submission.

    Args:
        submission_id (UUID): ID of the submission.

    Returns:
        FileResponse: ZIP file as a downloadable response.
    """
    zip_path = await get_submission_file_path(submission_id, db)
    return FileResponse(
        path=zip_path, filename=f"{submission_id}.zip", media_type="application/zip"
    )


@router.get(
    "/hackathon/{hackathon_id}/problem/{problem_statement_id}",
    response_model=List[SubmissionOut],
)
async def list_submissions_by_problem(
    hackathon_id: UUID,
    problem_statement_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get all submissions for a specific problem statement within a hackathon.

    Args:
        hackathon_id (UUID): ID of the hackathon.
        problem_statement_id (UUID): ID of the problem statement.

    Returns:
        List[SubmissionOut]: A list of all submissions.
    """
    submissions = await get_submissions_by_hackathon_and_problem(
        db, hackathon_id, problem_statement_id
    )

    if not submissions:
        raise HTTPException(status_code=404, detail="No submissions found.")

    return submissions


@router.get("/hackathon/{hackathon_id}/submission-count")
async def get_submission_count(hackathon_id: str, db: AsyncSession = Depends(get_db)):
    """
    Retrieve the total number of submissions for a given hackathon.

    Args:
        hackathon_id (str): ID of the hackathon.

    Returns:
        dict: Hackathon ID and the number of submissions made.
    """
    count = await count_submissions_for_hackathon(db, hackathon_id)
    return {"hackathon_id": hackathon_id, "submission_count": count}


@router.post("/", response_model=ScoringOut)
async def create_scoring(
    scoring_data: ScoringCreate, db: AsyncSession = Depends(get_db)
):
    """
    Create a new score entry for a submission.

    Args:
        scoring_data (ScoringCreate): Scoring details (submission ID, criteria, scores, etc.).

    Returns:
        ScoringOut: The newly created scoring object.
    """
    return await create_score(db, scoring_data)


@router.put("/{scoring_id}", response_model=ScoringOut)
async def update_scoring(
    scoring_id: UUID,
    score_update: ScoringUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Update an existing score entry.

    Args:
        scoring_id (UUID): ID of the scoring record.
        score_update (ScoringUpdate): Updated scoring fields.

    Returns:
        ScoringOut: The updated scoring record.

    Raises:
        HTTPException: If the scoring record does not exist.
    """
    scoring = await update_score(db, scoring_id, score_update)
    if not scoring:
        raise HTTPException(status_code=404, detail="Scoring not found")
    return scoring


@router.get("/submission/{submission_id}", response_model=ScoringOut)
async def get_score_for_submission(
    submission_id: UUID, db: AsyncSession = Depends(get_db)
):
    """
    Retrieve scoring details for a specific submission.

    Args:
        submission_id (UUID): ID of the submission.

    Returns:
        ScoringOut: The score associated with the submission.

    Raises:
        HTTPException: If no score exists for the submission.
    """
    scoring = await get_score_by_submission(db, submission_id)
    if not scoring:
        raise HTTPException(status_code=404, detail="Score not found")
    return scoring


@router.get("/hackathon/{hackathon_id}", response_model=list[ScoringOut])
async def get_scores_for_hackathon(
    hackathon_id: UUID, db: AsyncSession = Depends(get_db)
):
    """
    Get all scoring records for a specific hackathon.

    Args:
        hackathon_id (UUID): ID of the hackathon.

    Returns:
        List[ScoringOut]: List of scores for all submissions in the hackathon.
    """
    return await get_scores_by_hackathon(db, hackathon_id)


# -------------------------------generate--------------------------------------


@router.get("/hackathons/generate-from-job/{job_id}")
async def generate_hackathon(job_id: str, db: AsyncSession = Depends(get_db)):
    """
    Asynchronously generate a hackathon theme and description based on a job posting.

    Args:
        job_id (str): The UUID of the job.
        db (AsyncSession): The async database session.

    Returns:
        dict: Generated theme and description.
    """
    return await generate_hackathon_from_job(UUID(job_id), db)
