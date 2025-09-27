from pydantic import BaseModel
from enum import Enum
from uuid import UUID

class EmployerPostOfferLetterRequest(BaseModel):
    student_id: str 
    job_id: str     
    template_id: str
    start_date: str 

class StudentPostOfferLetterRequest(BaseModel):
    user_id: str 
    job_id: str

class StudentRejectOfferLetter(BaseModel):
    user_id: str 
    job_id: str


class OfferLetterTemplateOut(BaseModel):
    template_id: UUID
    template_file: str

    class Config:
        from_attributes = True

class OfferLetterEnumDTO(str, Enum):
    signed = "signed"
    unsigned = "unsigned"

class OfferLetterSchema(BaseModel):
    letter_id: UUID
    # student_id: UUID
    job_id: UUID
    # letter_file: str
    status: OfferLetterEnumDTO

    class Config:
        from_attributes = True

class StudentOfferLetterOut(BaseModel):
    job_title: str 
    company_name: str 
    offered_on: str
    offer_letter: OfferLetterSchema

class EmployerOfferLetterOut(BaseModel):
    # job_title: str 

    offer_letter: OfferLetterSchema
