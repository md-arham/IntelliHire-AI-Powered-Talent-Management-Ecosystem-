from fastapi import (
    APIRouter,
    Query,
    Depends,
    Form,
    UploadFile,
    File,
    HTTPException,
    BackgroundTasks,
)
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List, Annotated
from app.schemas.auth_schemas import UserRole
from app.database.db import get_db
from app.services.campusplacement_services import (
    get_students_by_batch,
    upload_resource,
    delete_resource,
    get_resources_by_user_college,
    download_resource,
    get_analytics_counts,
    get_all_active_jobs,
    recommend_job_to_batch,
    get_batch_years_for_college,
    get_recommended_jobs_for_student,
    handle_bulk_student_upload,
)
from app.schemas.campusplacement_schemas import JobBase, RecommendJobRequest
from app.database.models import User
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.utils.logger_config import logger

router = APIRouter(prefix="/api/campusplacement", tags=["Campus Placement"])


@router.get("/batch-students")
async def get_students_by_batch_api(
    batch_year: int = Query(..., description="Batch year, e.g., 2024"),
    officer_user_Id: UUID = Query(
        ..., description="User ID of the campus placement officer"
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve students belonging to a specific batch year for a given campus placement officer.

    - Uses the officer's user ID to identify the associated college.
    - Returns all students from that college for the specified batch year.

    Args:
        batch_year (int): The academic batch year (e.g., 2024).
        officer_user_Id (UUID): The user ID of the campus placement officer.

    Returns:
        List of student records for the specified batch and college.
    """
    try:
        return await get_students_by_batch(batch_year, officer_user_Id, db)
    except Exception as e:
        logger.error(f"Error fetching students for batch {batch_year}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve batch students")


@router.post("/create-resource")
async def upload_resource_api(
    current_user_id: UUID = Form(...),
    title: str = Form(...),
    description: str = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a learning or reference resource (PDF, doc, etc.) for student access.

    - Can be used by campus placement officers to share learning materials.
    - Metadata like title and description is stored along with the uploaded file.

    Args:
        current_user_id (UUID): User ID of the campus officer uploading the resource.
        title (str): Title of the resource.
        description (str, optional): Optional description of the file.
        file (UploadFile): The resource file.

    Returns:
        A confirmation message and resource metadata.
    """
    try:
        return await upload_resource(current_user_id, title, description, file, db)
    except Exception as e:
        logger.error(f"Error uploading resource: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload resource")


@router.delete("/delete-resource/{resource_id}")
async def delete_resource_api(
    resource_id: UUID,
    current_user_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a previously uploaded resource.

    - Only the owner (officer who uploaded) can delete the resource.

    Args:
        resource_id (UUID): The ID of the resource to be deleted.
        current_user_id (UUID): The user ID of the officer performing the deletion.

    Returns:
        A success confirmation if deletion is successful.
    """
    try:
        return await delete_resource(resource_id, current_user_id, db)
    except Exception as e:
        logger.error(f"Error deleting resource {resource_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete resource")


@router.get("/get-resource")
async def get_resources_by_user_college_api(
    current_user_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch all uploaded learning resources available to a specific college.

    - Retrieves resources uploaded by any officer in the same college as the current user.

    Args:
        current_user_id (UUID): User ID of the campus officer requesting the list.

    Returns:
        List of resources with metadata like title, description, and upload date.
    """
    try:
        return await get_resources_by_user_college(current_user_id, db)
    except Exception as e:
        logger.error(f"Error fetching resources for user {current_user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch resources")


@router.get("/download/{resource_id}")
async def download_resource_api(
    resource_id: UUID,
    current_user_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Download a specific learning resource uploaded by a campus placement officer.

    - Ensures the user has permission to access the resource from the same college.

    Args:
        resource_id (UUID): The ID of the resource to download.
        current_user_id (UUID): User ID of the campus officer initiating the download.

    Returns:
        File stream (PDF, doc, etc.) for download.
    """
    try:
        return await download_resource(resource_id, current_user_id, db)
    except Exception as e:
        logger.error(f"Error downloading resource {resource_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to download resource")


@router.get("/analytics/counts")
async def get_analytics_counts_api(
    campus_placement_officer_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch dashboard-level analytics for a campus placement officer.

    - Metrics may include:
        - Total registered students
        - Number of uploaded resources
        - Job recommendations
        - Placement progress

    Args:
        campus_placement_officer_id (UUID): Officer’s user ID.

    Returns:
        Dictionary containing key analytics metrics.
    """
    try:
        return await get_analytics_counts(campus_placement_officer_id, db)
    except Exception as e:
        logger.error(f"Error fetching analytics: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch analytics counts")


@router.get("/get-jobs", response_model=List[JobBase])
async def get_all_jobs(db: AsyncSession = Depends(get_db)):
    """
    Retrieve all active job listings available for campus placement recommendations.

    Returns:
        List of job postings with their details (title, description, skills, etc.).
    """
    try:
        return await get_all_active_jobs(db)
    except Exception as e:
        logger.error(f"Error fetching active jobs: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve active jobs")


@router.post("/recommend")
async def recommend_job_to_batch_year(
    data: RecommendJobRequest,
    current_user_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Recommend a job to all students in a specific batch year.

    - Can only be performed by authorized campus placement officers.
    - Triggers job recommendation logic and stores mappings in DB.

    Args:
        data (RecommendJobRequest): Contains job ID and batch year.
        current_user_id (UUID): Officer's user ID for authorization.

    Returns:
        Success message with count of students who received the recommendation.
    """
    try:
        result = await db.execute(
            select(User)
            .options(selectinload(User.placement_officer_profile))
            .where(User.user_id == current_user_id)
        )
        current_user = result.scalar_one_or_none()

        if current_user is None or current_user.role != UserRole.campus_officer:
            raise HTTPException(
                status_code=403, detail="Only campus officers can recommend jobs"
            )

        officer_id = current_user.placement_officer_profile.officer_id
        count = await recommend_job_to_batch(
            db, data.job_id, data.batch_year, officer_id
        )

        return {
            "message": f"Recommended to {count} students from batch year {data.batch_year}."
        }

    except Exception as e:
        logger.error(
            f"Error recommending job {data.job_id} to batch {data.batch_year}: {e}"
        )
        raise HTTPException(status_code=500, detail="Failed to recommend job to batch")


@router.get("/batches/years")
async def get_batch_years(
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Query(...),
):
    """
    Retrieve all batch years associated with the campus placement officer's college.

    - Helps in populating filters and dropdowns in UI for batch-wise operations.

    Args:
        current_user_id (UUID): User ID of the campus officer.

    Returns:
        Dictionary with list of distinct batch years (e.g., {"batch_years": [2023, 2024]}).
    """
    try:
        result = await db.execute(
            select(User)
            .options(selectinload(User.placement_officer_profile))
            .where(User.user_id == current_user_id)
        )
        user = result.scalar_one_or_none()

        if user is None or user.role != UserRole.campus_officer:
            raise HTTPException(
                status_code=403, detail="Only campus officers can view batch years"
            )

        college_id = user.placement_officer_profile.college_id
        years = await get_batch_years_for_college(db, college_id)

        if not years:
            logger.warning("No batch years found in the system")
            return {"batch_years": []}

        return {"batch_years": years}

    except Exception as e:
        logger.error(f"Error fetching batch years: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch batch years")


@router.get("/students/{user_id}/recommended-jobs", response_model=List[JobBase])
async def get_recommended_jobs_for_student_route(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get all job recommendations generated for a specific student.

    - Recommendations are personalized based on profile, resume, and skills.

    Args:
        user_id (UUID): User ID of the student.

    Returns:
        List of recommended job postings for the student.
    """

    try:
        return await get_recommended_jobs_for_student(db, user_id)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error(
            f"Unexpected error while fetching recommended jobs for {user_id}: {e}"
        )
        raise HTTPException(status_code=500, detail="Failed to fetch recommended jobs.")


@router.post("/bulk-upload")
async def bulk_student_upload(
    background_tasks: BackgroundTasks,
    user_id: Annotated[str, Form(description="Campus placement officer user ID")],
    excel_file: Annotated[
        UploadFile,
        File(
            description="Excel file containing student data with columns: full_name, email, student_id, batch (optional)"
        ),
    ],
    resume_zip: Annotated[
        UploadFile,
        File(description="ZIP file containing PDF resumes named as student_id.pdf"),
    ],
    db: AsyncSession = Depends(get_db),
):
    """
    Bulk upload students and their resumes for campus placement.

    - Only campus placement officers can access this endpoint.
    - Requires both an Excel sheet and a ZIP file of resumes.

    Excel Requirements:
        - Must include columns: `full_name`, `email`, `student_id`, `batch` (optional)
        - File must be .xlsx or .xls

    ZIP Requirements:
        - Must contain only PDFs
        - Each PDF named as {student_id}.pdf
        - File must be under 100MB

    Background processing:
        - Students are validated and registered in batches.
        - Resumes are parsed and linked to student profiles.
        - Email is sent to the officer with result Excel (credentials + status).

    Args:
        user_id (str): Campus placement officer's user ID.
        excel_file (UploadFile): Excel sheet with student data.
        resume_zip (UploadFile): ZIP file of student resumes.

    Returns:
        Initiation confirmation message with estimated processing status.
    """

    try:
        # Validate file types
        if not excel_file.filename.lower().endswith((".xlsx", ".xls")):
            raise HTTPException(
                status_code=400, detail="Excel file must be in .xlsx or .xls format"
            )

        if not resume_zip.filename.lower().endswith(".zip"):
            raise HTTPException(
                status_code=400, detail="Resume file must be in .zip format"
            )

        # Validate file sizes (10MB for Excel, 100MB for ZIP)
        if excel_file.size > 10 * 1024 * 1024:  # 10MB
            raise HTTPException(
                status_code=400, detail="Excel file size must be less than 10MB"
            )

        if resume_zip.size > 100 * 1024 * 1024:  # 100MB
            raise HTTPException(
                status_code=400, detail="Resume ZIP file size must be less than 100MB"
            )

        # Process the bulk upload
        result = await handle_bulk_student_upload(
            user_id=user_id,
            excel_file=excel_file,
            resume_zip=resume_zip,
            db=db,
            background_tasks=background_tasks,
        )

        return {
            "success": True,
            "data": result,
            "message": "Bulk upload initiated successfully. You will receive an email with the results.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in bulk upload: {e}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while processing the bulk upload",
        )
