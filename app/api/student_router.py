from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Any, Dict, List
from uuid import UUID
from app.database.db import get_db
from app.database.models import Student
from app.schemas.student_schemas import StudentResponse, StudentUpdateSchema
from app.services.student_service import StudentService, get_all_students, get_student

router = APIRouter(prefix="/api/students", tags=["Students"])


@router.get("/get_students/", response_model=List[StudentResponse])
async def list_students(db: AsyncSession = Depends(get_db)):
    """
        Retrieve all students from the database.

        Args:
            db (AsyncSession): Asynchronous database session.

        Returns:
            List[StudentResponse]: A list of all student records.
    """
    return await get_all_students(db)


@router.get("/get_student/{student_id}", response_model=StudentResponse)
async def retrieve_student(student_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Retrieve a single student's details by their student_id.

    Args:
        student_id (UUID): The unique identifier of the student.
        db (AsyncSession): Asynchronous database session.

    Returns:
        StudentResponse: The student record associated with the given student_id.
    """
    return await get_student(db, student_id)

@router.patch("/update_student/{user_id}", response_model=Dict[str, Any])
async def update_student(
    user_id: UUID, student_data: StudentUpdateSchema, db: AsyncSession = Depends(get_db)
):
    """
    Update student details across multiple tables using the user's ID.

    Args:
        user_id (UUID): The unique identifier of the user whose student data will be updated.
        student_data (StudentUpdateSchema): The fields to update for the student.
        db (AsyncSession): Asynchronous database session.

    Returns:
        Dict[str, Any]: A dictionary containing the update result or an error message.
    """
    try:
        # Find the student by user_id using async select
        result = await db.execute(select(Student).where(Student.user_id == user_id))
        student = result.scalars().first()
        if not student:
            raise HTTPException(
                status_code=404, detail="Student not found for this user_id."
            )
        # Update student using async service
        result = await StudentService.update_student(db, student.student_id, student_data)
        await db.commit()
        return result
    except HTTPException as e:
        await db.rollback()
        raise e
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to update student details: {str(e)}"
        )
