import logging
import json
from typing import Dict, List, Optional, Union

from app.utils.settings import client, settings

logger = logging.getLogger(__name__)


def generate_questions(
    topic: str,
    proficiency: str,
    num_questions: int = 1,
    existing_questions: Optional[List[str]] = None,
    max_retries: int = 3,
) -> List[str]:
    """
    Generate interview questions for a given topic and proficiency level.

    Args:
        topic: The topic/skill to generate questions for
        proficiency: The proficiency level (e.g., "Beginner", "Intermediate", "Advanced")
        num_questions: Number of questions to generate
        existing_questions: List of existing questions to avoid duplicates
        max_retries: Maximum number of retries on failure

    Returns:
        List of generated questions
    """
    if existing_questions is None:
        existing_questions = []

    prompt = f"""
    Generate {num_questions} unique technical interview question(s) about {topic} for a candidate at {proficiency} level.
    Each question should:
    - Be specific and focused on assessing understanding of {topic}
    - Be clear and unambiguous
    - Be appropriate for the {proficiency} level
    - Be answerable with a single, specific correct answer and several plausible incorrect answers
    - Not be duplicated in this list of existing questions: {existing_questions[:10]}
    
    Your response should be:
    - Only the question(s) with no additional text
    - Each question on a separate line
    - No numbering, no extra formatting
    """

    for attempt in range(max_retries):
        try:
            # Using the OpenAI client
            response = client.chat.completions.create(
                model=settings.MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )

            # Extract the response content
            response_text = response.choices[0].message.content.strip()
            questions = [q.strip() for q in response_text.split("\n") if q.strip()]

            # Filter out any questions that match existing ones
            new_questions = []
            for q in questions:
                if q not in existing_questions:
                    new_questions.append(q)

            if new_questions:
                return new_questions

        except Exception as e:
            logger.error(
                f"Error generating questions (attempt {attempt + 1}/{max_retries}): {e}"
            )

    # If all retries failed or no new questions were generated
    return []


def generate_answers(
    question: str, max_retries: int = 3
) -> Dict[str, Union[str, List[str]]]:
    """
    Generate a correct answer and three incorrect answers for a given question.

    Args:
        question: The question to generate answers for
        max_retries: Maximum number of retries on failure

    Returns:
        Dictionary with 'correct' (string) and 'incorrect' (list of 3 strings) answers
    """
    prompt = f"""
    For the following technical interview question:
    "{question}"
    
    Generate one correct answer and exactly three incorrect answers.
    
    Your response should be in the following JSON format:
    {{
        "correct": "The detailed correct answer",
        "incorrect": ["First incorrect answer", "Second incorrect answer", "Third incorrect answer"]
    }}
    
    Each incorrect answer should be plausible but clearly wrong. Make sure the answers are different from each other.
    """

    for attempt in range(max_retries):
        try:
            # Using the OpenAI client
            response = client.chat.completions.create(
                model=settings.MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )

            # Extract the response content
            response_text = response.choices[0].message.content.strip()

            # Parse the JSON response
            try:
                answers = json.loads(response_text)

                # Validate the format
                if (
                    isinstance(answers, dict)
                    and "correct" in answers
                    and "incorrect" in answers
                    and isinstance(answers["incorrect"], list)
                    and len(answers["incorrect"]) == 3
                ):
                    return answers

            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON response: {response_text}")

        except Exception as e:
            logger.error(
                f"Error generating answers (attempt {attempt + 1}/{max_retries}): {e}"
            )

    # If all retries failed or invalid format
    return {"correct": "", "incorrect": []}
