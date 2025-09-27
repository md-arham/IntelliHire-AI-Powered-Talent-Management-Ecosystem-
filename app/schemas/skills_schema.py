
from pydantic import BaseModel, validator
from typing import List




class Skills(BaseModel):
    skills: List[str]