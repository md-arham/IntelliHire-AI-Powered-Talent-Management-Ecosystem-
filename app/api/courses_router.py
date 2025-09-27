
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession


from app.services.courses_service import fetch_all_youtube_courses, fetch_all_coursera_courses, group_courses_by_aspirations
from app.database.db import get_db
from app.schemas.courses_schema import (
    
    CourseQueryParams,
    GroupedCoursesResponse,
    StudentCourseFetchRequest
)

router = APIRouter(prefix="/api/courses", tags=["Courses"])


@router.post("/list", response_model=GroupedCoursesResponse)
async def get_aspiration_course_mapping(
    payload: StudentCourseFetchRequest, db: AsyncSession = Depends(get_db)
):
    resp = await group_courses_by_aspirations(payload,db)
    if not resp:
        raise HTTPException(
            status_code=500, detail="Failed to fetch courses for the given student's aspirations"
        )
    # Returning a dictionary with aspiration names as key and lists of courses as values
    return resp

# No point for the following endopoint as it is completely redundant
@router.get("/allcourses")
async def get_courses(request:Request, params: CourseQueryParams = Depends()):
    """
    Fetch all courses from YouTube or Coursera based on the pricing filter.

    Args:
        params (CourseQueryParams): Query parameters including `query` and `pricing`.

    Returns:
        List[CourseItem]: A list of courses matching the search and pricing filter.

    Raises:
        JSONResponse: Returns a 500 error response if fetching from the selected provider fails.
    """
    pricing = params.pricing
    query = params.query
    if pricing == "free":
        courses = await fetch_all_youtube_courses(query, request)
        if not courses:
            return JSONResponse(
                status_code=500, content={"error": "Failed to fetch YouTube courses"}
            )
        return courses
    else:
        courses = await fetch_all_coursera_courses(query)
        if not courses:
            return JSONResponse(
                status_code=500, content={"error": "Failed to fetch Coursera courses"}
            )
        return courses
