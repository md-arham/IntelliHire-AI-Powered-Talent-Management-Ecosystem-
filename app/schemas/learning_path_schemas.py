from pydantic import BaseModel, UUID4
from typing import Dict, List

class LearningPathRequest(BaseModel):
    job_id: UUID4
    student_id: UUID4

    class Config:
        schema_extra = {
            "example": {
                "job_id": "8c843d64-3df9-4dfc-be21-304cb3fc3a77",
                "student_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            }
        }

class LearningPathQuery(BaseModel):
    job_id: UUID4
    student_id: UUID4

    class Config:
        schema_extra = {
            "example": {
                "job_id": "8c843d64-3df9-4dfc-be21-304cb3fc3a77",
                "student_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            }
        }

class LearningPathResponse(BaseModel):
    feedback_id: UUID4
    learning_path: Dict[str, List[str]]

    class Config:
        schema_extra = {
            "example": {
                "feedback_id": "0e46071a-c2b4-4160-9486-08e080d145da",
                "learning_path": {
                    "courses": [
                        "API Design Patterns",
                        "Error Handling in APIs with Python",
                        "Collaboration and Communication for Backend Teams",
                    ],
                    "resources": [
                        "Clean Code: A Handbook of Agile Software Craftsmanship book",
                        "Python Crash Course book",
                        "Codecademy's API Testing course",
                    ],
                },
            }
        }