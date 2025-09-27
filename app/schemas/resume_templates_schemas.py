from pydantic import BaseModel, HttpUrl
from uuid import UUID
from typing import Optional
from datetime import datetime

class ResumeTemplateBase(BaseModel):
    name: str
    preview_url: HttpUrl
    is_active: Optional[bool] = True

class ResumeTemplateCreate(ResumeTemplateBase):
    pass

class ResumeTemplateUpdate(BaseModel):
    name: Optional[str]
    preview_url: Optional[HttpUrl]
    is_active: Optional[bool]

class ResumeTemplateOut(ResumeTemplateBase):
    template_id: UUID
    created_at: datetime


    model_config = {
        "from_attributes": True
    }
