from typing import Literal, Optional
import uuid
from app.database.models.job_postings_models import JobCategoryType, JobOriginType
from pydantic import BaseModel


class InternshipFilterRequest(BaseModel):
    user_id: Optional[uuid.UUID] = None
    job_origin: Optional[JobOriginType] = None
    job_category_type: Optional[JobCategoryType] = JobCategoryType.INTERNSHIP
    work_type: Optional[Literal["Remote", "Onsite", "Hybrid"]] = None
    category: Optional[str] = None
    role: Optional[str] = None
    title: Optional[str] = None
    job_type: Optional[Literal["Full-Time", "Internship", "Contract", "Part-Time", "Campus_Driven"]] = None
    location: Optional[str] = None 
    page: int = 1                    
    page_size: int = 10          

#Schema to get a proper job summary during internship vector store
class JobDetailsSummary(BaseModel):
    skills: str
    degree_qualification: str
    college_type: str
    branch: str
    passed_out_year: Optional[int]
    location: str
    grade: Optional[float]
