from pydantic import BaseModel
from typing import Dict 
from uuid import UUID
class SkillsProficienciesRequest(BaseModel):
    user_id: UUID 
    skills: Dict[str, str]

class EvaluateQuestionsRequest(BaseModel):
    user_id: UUID 
    session_id: UUID 
    responses: Dict[str, str]