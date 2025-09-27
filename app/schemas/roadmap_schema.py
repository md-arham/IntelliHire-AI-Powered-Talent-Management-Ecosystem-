from pydantic import BaseModel, Field
from typing import List
from uuid import UUID

NUMBER_OF_PHASES = 4

class Course(BaseModel):
    title: str
    provider: str
    duration: str

class Phase(BaseModel):
    name: str
    duration: str
    objective: str
    skills_needed: List[str]
    tools: List[str]
    courses: List[Course]
    projects: List[str]

class Roadmap(BaseModel):
    title: str
    timeline: str
    phases: List[Phase] = Field(min_length=NUMBER_OF_PHASES, max_length=NUMBER_OF_PHASES)
    tips: List[str]

class GenerateRoadmapRequest(BaseModel):
    aspiration: str


class GenerateRoadmapAltRequest(BaseModel):
    user_id: str
    aspiration: str

class SaveRoadmapRequest(BaseModel):
    user_id: str 
    roadmap_id: str 
    role: str 
    roadmap: Roadmap

class GetRoadmapRequest(BaseModel):
    user_id: str 

class AspirationCreate(BaseModel):
    user_id: str
    aspirations: List[str]

# Optional: response schema
class AspirationResponse(BaseModel):
    aspiration_id: UUID
    aspiration_text: str
    class Config:
        from_attributes = True

class GenerateAllRoadmapsRequest(BaseModel):
    user_id: str
    aspirations: List[str]


class RoadmapResponse(BaseModel):
    roadmap_id: UUID 
    roadmap: Roadmap