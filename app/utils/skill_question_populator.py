import uuid
from sqlalchemy.orm import Session

from app.database.models.mock_interview_models import Question
from app.database.models.resume_extraction_models import Skill, PersonalInfo


def populate_questions_for_new_user(
    user_id: uuid.UUID, db: Session, questions_per_skill: int = 10
):
    """
    Populate questions for a specific user's skills that don't already have questions.

    Args:
        user_id (uuid.UUID): The UUID of the user whose skills need questions
        db (Session): Database session
        questions_per_skill (int): Number of questions to generate per skill

    Returns:
        int: The number of new questions generated
    """
    # Get the user's skills
    user_skills = (
        db.query(Skill.skill_name).filter(Skill.user_id == user_id).distinct().all()
    )
    user_skill_names = [skill[0] for skill in user_skills if skill[0]]

    if not user_skill_names:
        print(f"No skills found for user {user_id}")
        return 0

    print(f"Found {len(user_skill_names)} skills for user {user_id}")

    # Get skills that already have questions
    skills_with_questions = {}
    question_topics = db.query(Question.topic, Question.id).all()

    for topic, _ in question_topics:
        skills_with_questions[topic] = skills_with_questions.get(topic, 0) + 1

    # Find skills that need questions
    skills_needing_questions = []
    for skill in user_skill_names:
        if (
            skill not in skills_with_questions
            or skills_with_questions[skill] < questions_per_skill
        ):
            skills_needing_questions.append(skill)

    if not skills_needing_questions:
        print(f"All skills for user {user_id} already have questions")
        return 0

    print(f"Generating questions for {len(skills_needing_questions)} skills")

    # Get existing questions to avoid duplicates
    existing_questions = [q[0] for q in db.query(Question.question_text).all()]

    # Close this DB session as populate_database_from_skills will create its own
    db.close()

    # Generate questions only for the skills that need them
    # We'll create a custom function to handle just these skills
    return populate_questions_for_specific_skills(
        skills_needing_questions,
        questions_per_skill=questions_per_skill,
        existing_questions=existing_questions,
    )


def populate_questions_for_specific_skills(
    skills: list[str], questions_per_skill: int = 10, existing_questions=None
):
    """
    Populate questions for specific skills, regardless of user.

    Args:
        skills (list[str]): List of skill names to generate questions for
        questions_per_skill (int): Number of questions to generate per skill
        existing_questions (list): List of existing questions to avoid duplicates

    Returns:
        int: The number of new questions generated
    """
    from app.utils.db_populator import (
        populate_database_from_skills,
        get_distinct_skills_from_db as original_get_skills,
    )

    # Create a temporary wrapper function that only processes our specific skills
    def custom_get_distinct_skills_from_db(_):
        return skills

    # Replace with our custom function
    import app.utils.db_populator

    app.utils.db_populator.get_distinct_skills_from_db = (
        custom_get_distinct_skills_from_db
    )

    try:
        # Run the population with our modified function
        result = populate_database_from_skills(
            questions_per_skill=questions_per_skill,
            existing_questions=existing_questions,
        )

        # Calculate how many new questions were added
        new_questions_count = 0
        if existing_questions is not None:
            new_questions_count = len(result) - len(existing_questions)

        return new_questions_count

    finally:
        # Restore the original function
        app.utils.db_populator.get_distinct_skills_from_db = original_get_skills


def auto_populate_after_skills_added(user_id: uuid.UUID, db: Session):
    """
    Function to be called after skills are added to a user.
    This will automatically populate questions for any new skills.

    Args:
        user_id (uuid.UUID): The UUID of the user whose skills were added
        db (Session): Database session
    """
    # Get the user's personal info
    user = db.query(PersonalInfo).filter(PersonalInfo.id == user_id).first()

    if not user:
        print(f"User {user_id} not found")
        return

    print(f"Auto-populating questions for user: {user.first_name} {user.last_name}")

    # Populate questions for the user's skills
    new_questions = populate_questions_for_new_user(user_id, db)

    print(f"Added {new_questions} new questions for user {user_id}")
