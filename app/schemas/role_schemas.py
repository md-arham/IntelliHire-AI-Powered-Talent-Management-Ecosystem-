from typing import List, Optional
from pydantic import BaseModel

class RoleAssignment(BaseModel):
    user: str
    role: str
    domain: Optional[str] = None

class RoleResponse(BaseModel):
    name: str
    users: List[str]
    
