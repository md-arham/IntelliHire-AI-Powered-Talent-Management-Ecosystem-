from pydantic import BaseModel, UUID4
from typing import Optional


class CollegeBase(BaseModel):
    name: str
    location: Optional[str] = None
    affiliated_university: Optional[str] = None


class CollegeCreate(CollegeBase):
    pass


class CollegeUpdate(CollegeBase):
    pass


class CollegeOut(CollegeBase):
    college_id: UUID4

    class Config:
        from_attributes = True
