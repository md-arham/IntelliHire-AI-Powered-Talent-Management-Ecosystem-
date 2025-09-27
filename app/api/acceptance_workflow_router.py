from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.db import get_db

from app.schemas.acceptance_workflow_schemas import AcceptanceActionRequest

from app.services.acceptance_workflow_service import (
    reject_student,
    shortlist_student,
)

from app.services.learning_path_service import generate_learning_path

router = APIRouter(prefix="/api/acceptance_flow", tags=["Acceptance Workflow"])


@router.post(
    "/reject",
    summary="Reject a student's job application",
    response_description="Confirmation of rejection",
    status_code=status.HTTP_200_OK,
)
async def reject(
    request: AcceptanceActionRequest,
    db: Session = Depends(get_db),
):
    """
    Reject a student's application for a specific job.

    - **request.job_id**: UUID of the job
    - **request.student_user_id**: UUID of the student's user
    """
    try:
        result = await reject_student(db, request.job_id, request.student_user_id)
        await generate_learning_path(db, result["student_id"], request.job_id)
        return {"detail": "Application rejected successfully", "result": result}
    except HTTPException as e:
        # Propagate HTTP exceptions
        raise e
    except Exception as e:
        # Log unexpected errors and return 500
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post(
    "/shortlist",
    summary="Shortlist a student's job application",
    response_description="Confirmation of shortlisting",
    status_code=status.HTTP_200_OK,
)
async def shortlist(
    request: AcceptanceActionRequest,
    db: Session = Depends(get_db),
):
    """
    Shortlist a student's application and advance them to L2 stage.

    - **request.job_id**: UUID of the job
    - **request.student_user_id**: UUID of the student's user
    """
    try:
        result = await shortlist_student(db, request.job_id, request.student_user_id)
        return {"detail": "Application shortlisted successfully", "result": result}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
