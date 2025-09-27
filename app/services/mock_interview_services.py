import random
from uuid import UUID, uuid4
from fastapi.exceptions import HTTPException
from fuzzywuzzy import process
from sqlalchemy import select
from sqlalchemy.sql import func
from app.database.models import PersonalInfo
from app.database.models.enums_models import ResultEnum
from app.database.models.mock_interview_models import (
    Answer,
    MockInterviewResponse,
    MockInterviewSession,
    Question,
)
from app.database.models.resume_extraction_models import Skill
from app.database.models.students_models import Student
from app.utils.logger_config import logger
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.settings import settings

async def fetch_user_skills(db: AsyncSession, user_id: UUID) -> list[dict]:
    """
    Fetch all technical skills for a user based on their resume.

    This endpoint retrieves skills linked to a user's resume if their category is 
    'Programming Language' or 'Tool/Technology'. The user ID is mapped to the student's resume 
    via the Student and PersonalInfo tables.

    Args:
        user_id (UUID): The unique identifier of the user.
        db (Session): SQLAlchemy database session dependency.

    Returns:
        JSONResponse: A success response containing a list of skill dictionaries with 
        fields: id, user_id, skill_name, and category.

    Raises:
        HTTPException 404: If no student, personal info, or skills are found.
        HTTPException 400: For any bad request or invalid input.
        HTTPException 500: For internal server errors.
    """
    try:
        stmt = (
            select(Skill)
            .join(PersonalInfo, Skill.user_id == PersonalInfo.id)
            .join(Student, PersonalInfo.student_id == Student.student_id)
            .filter(Student.user_id == user_id)
        )
        skill_response = await db.execute(stmt)
        skills = skill_response.scalars().all()

        if not skills:
            logger.info(f"No skills found for user_id: {user_id}")
            raise HTTPException(status_code=404, detail="No skills found for the provided user_id")

        skills_list = [
            {
                "id": str(skill.id),
                "user_id": str(skill.user_id),
                "skill_name": skill.skill_name,
                "category": skill.category,
            }
            for skill in skills
        ]

        logger.info(f"Fetched {len(skills_list)} skills for user_id: {user_id}")
        return skills_list
    
    except Exception as e:
        logger.error(f"Error fetching skills for user_id {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error unable to fetch skills")


async def fetch_questions_by_skills(
    db: AsyncSession, user_id: UUID, skills_proficiencies: dict[str, str]
):
    """
    Retrieve 10 mock interview questions based on user's selected skills and their proficiencies.

    The function matches skill names to question topics using fuzzy logic, distributes 
    question count fairly among matched topics, and creates a new interview session 
    storing the generated questions.

    Args:
        db (AsyncSession): SQLAlchemy async DB session.
        user_id (str): UUID of the user as a string.
        skills_proficiencies (dict[str, str]): A dictionary mapping skill names to proficiencies.

    Returns:
        tuple[list[dict], str]: List of question dicts with choices, and the session ID.

    Raises:
        HTTPException: 
            - 400 for invalid inputs.
            - 404 if no student or no matching topics/questions are found.
            - 500 for unexpected errors.
    """
    
    try:
        if not isinstance(skills_proficiencies, dict) or not skills_proficiencies:
            logger.error("Invalid skills_proficiencies: must be a non-empty dict")
            raise HTTPException(
                status_code=400,
                detail="Skills and proficiencies must be a non-empty dictionary",
            )

        if len(skills_proficiencies) > settings.MAX_SKILL_PROFICIENCIES:
            logger.error(f"Too many skills provided: {len(skills_proficiencies)}, max 4 allowed")
            raise HTTPException(status_code=400, detail="Maximum 4 skills allowed")

        for skill, proficiency in skills_proficiencies.items():
            if not isinstance(skill, str) or not isinstance(proficiency, str):
                logger.error(f"Invalid skill or proficiency: {skill} - {proficiency}")
                raise HTTPException(
                    status_code=400, detail="Skills and proficiencies must be strings"
                )

        # Fetch student
        result = await db.execute(select(Student).where(Student.user_id == user_id))
        student = result.scalars().first()
        if not student:
            logger.info(f"No student found for user_id: {user_id}")
            raise HTTPException(status_code=404, detail="No student exists with that id")

        # Fetch all backend topics
        result = await db.execute(select(Question.topic).distinct())
        backend_topics = [row[0] for row in result.all()]

        matched_skills = {}
        for skill, proficiency in skills_proficiencies.items():
            match, score = process.extractOne(skill, backend_topics)
            if score >= settings.THRESHOLD_VALUE_MOCK:
                matched_skills[match] = proficiency
            else:
                logger.warning(f"No good match found for skill: {skill} (score: {score})")

        if not matched_skills:
            logger.error("No valid backend topic matches for provided skills")
            raise HTTPException(status_code=404, detail="No matching topics found")

        # Distribute 10 questions
        num_skills = len(matched_skills)
        total_points = 10
        base = total_points // num_skills
        remainder = total_points % num_skills
        distribution = [base + 1 if i < remainder else base for i in range(num_skills)]

        skill_items = list(matched_skills.items())
        random.shuffle(skill_items)
        skill_distribution = {
            skill: count for (skill, _), count in zip(skill_items, distribution)
        }

        question_objs = []
        for skill, proficiency in skill_items:
            result = await db.execute(
                select(Question)
                .where(Question.topic == skill, Question.proficiency == proficiency)
                .order_by(func.random())
                .limit(skill_distribution[skill])
            )
            questions = result.scalars().all()
            question_objs.extend(questions)

            logger.info(f"Fetched {len(questions)} questions for matched skill: {skill}")

        if not question_objs:
            raise HTTPException(status_code=404, detail="No questions found")

        question_ids = [q.id for q in question_objs]

        # Fetch answers in one batch
        answer_result = await db.execute(
            select(Answer).where(Answer.question_id.in_(question_ids))
        )
        answers = answer_result.scalars().all()
        answer_map = {a.question_id: a for a in answers}

        # Build final question dicts
        all_questions = []
        for question in question_objs:
            answer = answer_map.get(question.id)
            all_questions.append({
                "id": str(question.id),
                "question_text": question.question_text,
                "topic": question.topic,
                "proficiency": question.proficiency,
                "choices": answer.choices if answer else [],
            })

        if len(all_questions) < 10:
            logger.warning(f"Only {len(all_questions)} questions found, expected 10")

        random.shuffle(all_questions)
        all_questions = all_questions[:10]

        session_id = uuid4()
        new_session = MockInterviewSession(
            session_id=session_id, student_id=student.student_id
        )
        db.add(new_session)
        await db.flush()  # flush before adding responses for FK integrity

        responses = [
            MockInterviewResponse(
                session_id=session_id,
                response_id=uuid4(),
                question_id=question["id"],
            )
            for question in all_questions
        ]
        db.add_all(responses)
        await db.commit()

        logger.info(
            f"Added {len(all_questions)} questions to session {session_id} for {user_id}"
        )
        return all_questions, str(session_id)

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


async def evaluate_answers(
    db: AsyncSession, user_id: UUID, session_id: UUID, responses: dict[str, str]
):
    """
    Evaluate a user's submitted answers against correct answers and store the results.

    It validates the student and session, retrieves all correct answers in bulk, compares 
    each response, updates the result status, and stores the final score in the session.

    Args:
        db (AsyncSession): SQLAlchemy async database session.
        user_id (str): UUID of the user as a string.
        session_id (str): UUID of the session as a string.
        responses (dict[str, str]): A mapping of question_id to user-selected answer_id.

    Returns:
        int: The user's total score (number of correct answers).

    Raises:
        HTTPException: 
            - 404 if student or session not found.
            - 500 on internal server error.
    """
    try:
        # Fetch student
        student_stmt = select(Student).where(Student.user_id == user_id)
        student_result = await db.execute(student_stmt)
        student = student_result.scalars().first()
        if not student:
            logger.info(f"No student found for user_id: {user_id}")
            raise HTTPException(status_code=404, detail="No student exists with that id")

        # Fetch all answers in one go
        question_ids = list(responses.keys())
        answer_stmt = select(Answer).where(Answer.question_id.in_(question_ids))
        answer_result = await db.execute(answer_stmt)
        answers = answer_result.scalars().all()
        correct_answers_map = {
            str(answer.question_id): answer.correct_answer_id for answer in answers
        }

        # Validate session
        session_stmt = select(MockInterviewSession).where(
            MockInterviewSession.session_id == session_id,
            MockInterviewSession.student_id == student.student_id,
        )
        session_exec_result = await db.execute(session_stmt)
        session_record = session_exec_result.scalars().first()
        if not session_record:
            logger.info(f"No session found for session_id: {session_id}")
            raise HTTPException(status_code=404, detail="No session with that id")

        score = 0
        for question_id, user_answer_id in responses.items():
            is_correct = user_answer_id == correct_answers_map.get(question_id)
            result_enum = ResultEnum.correct if is_correct else ResultEnum.wrong
            if is_correct:
                score += 1

            # Update response record
            response_stmt = select(MockInterviewResponse).where(
                MockInterviewResponse.session_id == session_id,
                MockInterviewResponse.question_id == question_id,
            )
            response_result = await db.execute(response_stmt)
            response_record = response_result.scalars().first()
            if response_record:
                response_record.user_answer_id = user_answer_id
                response_record.result = result_enum
                db.add(response_record)

        session_record.score = score
        db.add(session_record)
        await db.commit()

        logger.info(
            f"Stored results in mock_interview_responses, score: {score}, session: {session_id}, user: {user_id}"
        )
        return score

    except Exception as e:
        logger.error(f"Unexpected error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


async def get_score(db: AsyncSession, user_id: UUID, session_id: UUID):
    try:
        """
        Retrieve the final score of a specific mock interview session for a user.

        Validates user and session before returning the score stored during evaluation.

        Args:
            db (AsyncSession): SQLAlchemy async DB session.
            user_id (str): UUID of the user as a string.
            session_id (str): UUID of the mock interview session.

        Returns:
            int: The user's score for the given session.

        Raises:
            HTTPException: 
                - 404 if student or session not found.
                - 500 on internal server error.
        """
        # Fetch student asynchronously
        result = await db.execute(select(Student).where(Student.user_id == user_id))
        student = result.scalars().first()

        if not student:
            logger.info(f"No student found for user_id: {user_id}")
            raise HTTPException(status_code=404, detail="No student exists with that id")

        # Fetch session and score
        result = await db.execute(
            select(MockInterviewSession).where(
                MockInterviewSession.session_id == session_id,
                MockInterviewSession.student_id == student.student_id,
            )
        )
        session = result.scalars().first()

        if not session:
            logger.info(f"No session found for session_id: {session_id}")
            raise HTTPException(status_code=404, detail="Session not found")

        return session.score

    except Exception as e:
        logger.error(f"Unexpected error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")