from typing import Dict, List, Optional
from pydantic import BaseModel, UUID4


class CourseItem(BaseModel):
    course_id: UUID4
    title: str
    level: str
    duration: str
    url: str
    status: str
    progress_percent: int
    rating: float = None
    imageUrl: str = None
    image: str = None
    
    class Config:
        from_attributes = True

class GroupedCoursesResponse(BaseModel):
    courses: Dict[str, List[CourseItem]]

class AllCourses(BaseModel):
    id: str
    title: str
    description: str
    instructor: str
    category: str
    duration: str
    level: str
    imageUrl: str
    image: str
    courseUrl: str
    rating: float
    enrolled: int
    topics: List[str]
    platform: str
    pricingType: str

class CourseQueryParams(BaseModel):
    query: str = "programming course"
    pricing: str = "free" 

class StudentCourseCreate(BaseModel):
    user_id: UUID4
    roadmap_id: Optional[UUID4] = None
    # roadmap_json: dict  # Accepts any JSON objects

class StudentCourseResponse(BaseModel):
    course_id: UUID4
    student_id: UUID4
    roadmap_id: Optional[UUID4]
    status: str
    progress_percent: int
    last_accessed: Optional[str]
    title: str
    level: str
    duration: str
    url: str
    rating: float
    imageUrl: str
    image: str
    aspiration_name : str

class StudentCourseFetchRequest(BaseModel):
    user_id: UUID4
