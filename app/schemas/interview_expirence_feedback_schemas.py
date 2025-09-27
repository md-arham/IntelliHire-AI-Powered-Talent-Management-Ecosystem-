from pydantic import BaseModel, Field
from uuid import UUID
from typing import Optional
import enum

# class ExperienceRating(str, enum.Enum):
#     EXCELLENT = "EXCELLENT"
#     GOOD = "GOOD"
#     AVERAGE = "AVERAGE"
#     POOR = "POOR"

# class RelevanceRating(str, enum.Enum):
#     VERY_RELEVANT = "VERY_RELEVANT"
#     SOMEWHAT_RELEVANT = "SOMEWHAT_RELEVANT"
#     NOT_RELEVANT = "NOT_RELEVANT"

# class ClarityRating(str, enum.Enum):
#     YES = "YES"
#     SOMEWHAT = "SOMEWHAT"
#     NO = "NO"

# class EaseOfUseRating(str, enum.Enum):
#     VERY_EASY = "VERY_EASY"
#     EASY = "EASY"
#     DIFFICULT = "DIFFICULT"
#     VERY_DIFFICULT = "VERY_DIFFICULT"
class ExperienceRating(str, enum.Enum):
    Excellent = "Excellent"
    Good = "Good"
    Average = "Average"
    Poor = "Poor"

class RelevanceRating(str, enum.Enum):
    VeryRelevant = "VeryRelevant"
    SomewhatRelevant = "SomewhatRelevant"
    NotRelevant = "NotRelevant"

class ClarityRating(str, enum.Enum):
    Yes = "Yes"
    Somewhat = "Somewhat"
    No = "No"

class EaseOfUseRating(str, enum.Enum):
    VeryEasy = "VeryEasy"
    Easy = "Easy"
    Difficult = "Difficult"
    VeryDifficult = "VeryDifficult"

class InterviewExperienceFeedbackCreate(BaseModel):
    session_id: UUID
    job_id: UUID
    overall_experience: ExperienceRating
    question_relevance: RelevanceRating
    question_clarity: ClarityRating
    ease_of_use: EaseOfUseRating
    suggestions: Optional[str] = Field(
        None, description="Suggestions for improving the interview process"
    )
