from pydantic import BaseModel

class AcceptanceActionRequest(BaseModel):
    student_user_id: str 
    job_id: str