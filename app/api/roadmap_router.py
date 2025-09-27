from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
# from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database.db import get_db
from app.database.models.aspiration_models import Aspiration
from app.database.models.roadmaps_models import Roadmaps
from app.database.models.students_models import Student
from app.schemas.roadmap_schema import (
    GenerateAllRoadmapsRequest,
    GetRoadmapRequest,
    Roadmap,
    RoadmapResponse
)
from app.services.roadmap_services import (
    store_aspirations,
    store_roadmap,
    generate_roadmaps_async
)

from app.utils.logger_config import logger

router = APIRouter(tags=["Roadmap"])

@router.get("/api/roadmap/aspirations/{user_id}")
async def get_aspirations(user_id: str, db: AsyncSession = Depends(get_db)) -> List[str]:
    try:
        result = await db.execute(select(Student).where(Student.user_id == user_id))
        student = result.scalar_one_or_none()
        if not student:
            return []

        result = await db.execute(
            select(Aspiration).where(Aspiration.student_id == student.student_id)
        )
        aspirations = result.scalars().all()

        return [aspiration.aspiration_text for aspiration in aspirations]

    except Exception as e:
        logger.error(f"An error occurred in Roadmaps Router: {e}")
        raise HTTPException(detail="An error occurred", status_code=500)


@router.post("/api/roadmap/get", response_model=List[RoadmapResponse])
async def get_roadmap(request: GetRoadmapRequest, db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(
            select(Student).where(Student.user_id == request.user_id)
        )
        student = result.scalar_one_or_none()
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student not found",
            )

        result = await db.execute(
            select(Roadmaps).where(Roadmaps.student_id == student.student_id)
        )
        results = result.scalars().all()

        if not results:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No roadmaps found for this student",
            )

        roadmaps = [
            RoadmapResponse(
                roadmap_id=result.roadmap_id,
                roadmap=Roadmap.model_validate(result.data)
            )
            for result in results
        ]
        return roadmaps

    except Exception as e:
        logger.error(f"Error fetching roadmap: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching the roadmap",
        )

@router.post("/api/roadmap/generate-all")
async def generate_all_roadmaps(
    payload: GenerateAllRoadmapsRequest,
    db: AsyncSession = Depends(get_db)
):
    try:
        result = await db.execute(
            select(Student).where(Student.user_id == payload.user_id)
        )
        student = result.scalar_one_or_none()
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        await store_aspirations(db, student.student_id, payload.aspirations)

        roadmaps = []
        async for roadmap, aspiration in generate_roadmaps_async(payload.aspirations):
            roadmap_instance = await store_roadmap(
                db, student.student_id, aspiration, roadmap
            )
            logger.info(
                f"Stored roadmap for aspiration {aspiration} for student {student.student_id}"
            )
            roadmaps.append(roadmap_instance)

        return {"status": "success :)"}

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in generate_all_roadmaps: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


