from pydantic import BaseModel ,EmailStr
from typing import Optional
from typing import List
import uuid
from uuid import UUID





class QuestionAnswerUpdate(BaseModel):
    question_id : str
    user_answer : str

class BulkUpdateAnswerRequest(BaseModel):
    session_id: UUID
    answers: List[QuestionAnswerUpdate]

#schemas code
class ShortlistedCandidate(BaseModel):
    full_name: str
    email: str
    score: float
    status: str
    user_id: uuid.UUID
    strengths_of_candidate: List[str]

class ShortlistedCandidatesResponse(BaseModel):
    status: str
    candidates: List[ShortlistedCandidate]

class AnswerRequest(BaseModel):
    question_id: str
    question:str
    answer: str
 
class GenrateQuestions(BaseModel):
    questions: List[str] = []
 
class AnswerEval(BaseModel):
    answer_analysis : str = ""
    score: float = 0.0
    reason : str = ""

class FullInterviewAnalysis(BaseModel):
    feedback_summary_student: str = ""  # Recruiter
    # feedback_summary_recruiter: str | None = None
    strengths_of_candidate: List[str] = []  # Recruiter
    areas_of_improvement: List[str] = []# Student
    overall_score_out_of_5: float = 0.0 # Recruiter and Student
    skill_recommendations: List[str] = [] # Student
 
 
class InterviewResponse(BaseModel):
    question_id: str
    question: str
    user_answer: str
    individual_analysis: Optional[str] = None
    individual_score: Optional[float] = None
    reason_for_score_given: Optional[str] = None
 
 
class CompleteInterviewRequest(BaseModel):
    responses: List[InterviewResponse]
 
class StoreQuestionsRequest(BaseModel):
    student_id: uuid.UUID
    role: str
    resume_text: str
    audio_link: Optional[str] = None
    is_video_enabled: Optional[bool] = False

class StoreAnswerEvaluationRequest(BaseModel):
    session_id: uuid.UUID
    question_id: str
    # question: str
    user_answer: str

# class StoreCompleteInterviewRequest(BaseModel):
#     session_id: uuid.UUID
#     responses: List[InterviewResponse]

class StoreQuestionsRequest(BaseModel):
    student_id: uuid.UUID
    role: str
    resume_text: str
    audio_link: Optional[str] = None
    is_video_enabled: Optional[bool] = False

# class StoreAnswerEvaluationRequest(BaseModel):
#     session_id: uuid.UUID
#     question_id: str
#     question: str
#     user_answer: str

class StoreCompleteInterviewRequest(BaseModel):
    session_id: uuid.UUID
    job_id: uuid.UUID
    # feedback_type: str
    # responses: List[InterviewResponse]