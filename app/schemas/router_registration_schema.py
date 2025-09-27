from pydantic import BaseModel
from typing import Optional, Literal
from enum import Enum

class APIRegistration(BaseModel):
    role: str
    domain: str
    object: str
    path: str  # can be prefix or exact path
    method: Optional[str] = None  # e.g. GET, POST, etc. Optional
    effect: Literal["allow", "deny"] = "allow"

class EffectEnum(str, Enum):
    allow = "allow"
    deny = "deny"