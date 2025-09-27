from typing import List, Optional
from pydantic import BaseModel

class PolicyBase(BaseModel):
    subject: str
    domain: str
    object: str
    action: str
    effect: Optional[str] = "allow"

class PolicyCreate(PolicyBase):
    pass

class PolicyDelete(PolicyBase):
    pass

class PolicyResponse(PolicyBase):
    id: int


class BatchOperation(BaseModel):
    type: str  # 'add_policy', 'remove_policy', etc.
    params: List[str]

class BatchOperationRequest(BaseModel):
    operations: List[BatchOperation]

class BatchOperationResponse(BaseModel):
    results: List[bool]