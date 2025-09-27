import time
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.db import sessionLocal
from app.database.models.mock_interview_models import Answer, Question
from app.database.models.resume_extraction_models import Skill

# Removing this import since the function doesn't exist
# from app.services.db_services import question_exists
from app.utils.question_generator import generate_answers, generate_questions


# Define the question_exists function here since it doesn't exist in db_services.py
def question_exists(db: Session, question_text: str) -> bool:
    """
    Check if a question with the given text already exists in the database.

    Args:
        db (Session): Database session
        question_text (str): The question text to check

    Returns:
        bool: True if the question exists, False otherwise
    """
    # Do a case-insensitive search for the question
    existing = (
        db.query(Question)
        .filter(func.lower(Question.question_text) == func.lower(question_text))
        .first()
    )
    return existing is not None


def get_distinct_skills_from_db(db: Session):
    """
    Fetches all distinct skill names from the skills table.

    Args:
        db (Session): Database session

    Returns:
        list: List of distinct skill names
    """
    distinct_skills = db.query(Skill.skill_name).distinct().all()
    return [skill[0] for skill in distinct_skills if skill[0]]


def get_skills_with_questions(db: Session):
    """
    Fetches all skills that already have questions in the database.

    Args:
        db (Session): Database session

    Returns:
        dict: Dictionary with skill names as keys and the count of questions as values
    """
    skills_with_questions = {}

    # Get all distinct topics from questions table
    question_topics = (
        db.query(Question.topic, func.count(Question.id)).group_by(Question.topic).all()
    )

    for topic, count in question_topics:
        skills_with_questions[topic] = count

    return skills_with_questions


def populate_database_from_skills(
    questions_per_skill: int = 10,
    proficiency_levels: list[str] = None,
    minimum_questions_threshold: int = 5,
    existing_questions=None,
):
    """
    Populates the database with questions and answers for each skill found in the skills table.
    Only generates questions for skills that don't have enough questions already.

    Args:
        questions_per_skill (int): Target number of questions to have per skill
        proficiency_levels (list[str]): List of proficiency levels
        minimum_questions_threshold (int): Minimum threshold below which we'll generate questions
                                          for skills with existing questions
        existing_questions (list): Optional list of existing questions to check for duplicates
    """
    # No longer importing the question_exists function here

    if proficiency_levels is None:
        proficiency_levels = [
            "Beginner (0-3 years experience)",
            "Intermediate (3-7 years experience)",
            "Advanced (8+ years experience)",
        ]

    db = sessionLocal()

    if existing_questions is None:
        existing_questions = []

    try:
        # Load existing questions to avoid duplicates
        db_questions = db.query(Question.question_text).all()
        for q in db_questions:
            if q[0] not in existing_questions:
                existing_questions.append(q[0])
        print(f"Loaded {len(existing_questions)} existing questions from database")

        # Get all distinct skills from the database and sort them alphabetically for consistent order
        all_skills = sorted(get_distinct_skills_from_db(db))

        if not all_skills:
            print(
                "No skills found in the resume_extraction tables. Please add skills first."
            )
            return existing_questions

        print(f"Found {len(all_skills)} distinct skills in the database")

        # Get all skills that already have questions
        skills_with_questions = get_skills_with_questions(db)
        print(f"Found {len(skills_with_questions)} skills with existing questions")
        print(f"Target: {questions_per_skill} questions per skill")

        # Print skills that already have questions and their counts
        if skills_with_questions:
            print("\nSkills with existing questions:")
            for skill, count in sorted(skills_with_questions.items()):
                print(f"  - {skill}: {count}/{questions_per_skill} questions")

        skills_to_generate = []
        skills_skipped = []

        # First, determine which skills need questions
        for skill in all_skills:
            existing_count = skills_with_questions.get(skill, 0)

            # If we already have enough questions for this skill, skip it
            if existing_count >= questions_per_skill:
                skills_skipped.append(
                    (
                        skill,
                        f"already has {existing_count} questions (target: {questions_per_skill})",
                    )
                )
                continue

            # Calculate how many questions we need to generate for this skill
            questions_to_generate = questions_per_skill - existing_count

            # FIXED LOGIC: Skip only if the skill already has some questions AND
            # the number of existing questions is close to target (within minimum_threshold)
            if (
                existing_count > 0
                and questions_to_generate < minimum_questions_threshold
            ):
                skills_skipped.append(
                    (
                        skill,
                        f"already has {existing_count} questions and only needs {questions_to_generate} more (min threshold: {minimum_questions_threshold})",
                    )
                )
                continue

            # Add this skill to our list to generate questions for
            skills_to_generate.append((skill, questions_to_generate))

        # Print skills we're skipping
        if skills_skipped:
            print("\nSkipping skills:")
            for skill, reason in skills_skipped:
                print(f"  - {skill}: {reason}")

        # Print skills we'll generate questions for
        if skills_to_generate:
            print("\nGenerating questions for the following skills:")
            for skill, count in skills_to_generate:
                print(f"  - {skill}: {count} questions needed")
        else:
            print("\nNo skills need additional questions at this time.")
            return existing_questions

        # Now process each skill we need to generate questions for
        for skill, questions_to_generate in skills_to_generate:
            print(f"\n{'=' * 40}")
            print(f" Generating {questions_to_generate} questions for {skill} ")
            print(f"{'=' * 40}")

            # Generate questions for each proficiency level
            questions_per_level = questions_to_generate // len(proficiency_levels)
            remainder = questions_to_generate % len(proficiency_levels)

            for proficiency in proficiency_levels:
                # Adjust for remainder if needed
                level_questions = questions_per_level
                if remainder > 0:
                    level_questions += 1
                    remainder -= 1

                if level_questions <= 0:
                    continue

                total_saved = 0
                attempts = 0
                max_attempts = level_questions * 3

                print(f"\n--- Generating for {skill} - {proficiency} ---")

                while total_saved < level_questions and attempts < max_attempts:
                    attempts += 1

                    questions = generate_questions(
                        topic=skill,
                        proficiency=proficiency,
                        num_questions=1,
                        existing_questions=existing_questions,
                    )

                    if not questions:
                        continue

                    question_text = questions[0].strip()
                    if not question_text:
                        continue

                    if question_exists(db, question_text):
                        print(
                            f"Question already exists, skipping: {question_text[:50]}..."
                        )
                        continue

                    total_saved += 1
                    print(f"\nGenerated question {total_saved}:")
                    print(f'"{question_text}"')
                    print("Generating answers...")

                    answer_data = generate_answers(question_text, max_retries=3)
                    correct = answer_data["correct"]
                    incorrect = answer_data["incorrect"]

                    if (
                        not correct
                        or not isinstance(incorrect, list)
                        or len(incorrect) != 3
                    ):
                        total_saved -= 1
                        print("Failed to generate valid answers, skipping question")
                        continue

                    question_id = uuid.uuid4()
                    question = Question(
                        id=question_id,
                        question_text=question_text,
                        topic=skill,
                        proficiency=proficiency,
                    )
                    db.add(question)

                    all_options = incorrect + [correct]
                    option_map = {str(uuid.uuid4()): text for text in all_options}
                    correct_id = next(k for k, v in option_map.items() if v == correct)

                    answer = Answer(
                        id=uuid.uuid4(),
                        question_id=question_id,
                        choices=option_map,
                        correct_answer_id=correct_id,
                    )
                    db.add(answer)

                    try:
                        db.commit()

                        existing_questions.append(question_text)
                        print("Saved to database ✓")

                        # Update our count of questions for this skill
                        skills_with_questions[skill] = (
                            skills_with_questions.get(skill, 0) + 1
                        )

                    except Exception as e:
                        db.rollback()
                        print(f"Failed to save question: {e}")
                        total_saved -= 1

                    time.sleep(1)

                print(
                    f"\n✓ {skill} [{proficiency}] - {total_saved}/{level_questions} questions saved"
                )

    except Exception as e:
        print(f"Error in populate_database_from_skills: {e}")
        db.rollback()
    finally:
        db.close()

    return existing_questions


def main():
    """
    Main function to run the database population process
    """
    x = 60
    print("=" * x)
    print("Question Generator Based on Student Skills".center(x))
    print("=" * x)

    questions_per_skill = 10
    all_questions = []

    print("\nGENERATING QUESTIONS")
    print("-" * x)

    start_time = time.time()

    all_questions = populate_database_from_skills(
        questions_per_skill=questions_per_skill,
        existing_questions=all_questions,
    )

    end_time = time.time()
    elapsed_time = end_time - start_time

    db = sessionLocal()
    skills_count = len(get_distinct_skills_from_db(db))
    db.close()

    actual_questions = len(all_questions)

    print("\n" + "=" * x)
    print("GENERATION COMPLETE".center(x))
    print(f"Generated {actual_questions} unique questions")
    print(f"Across {skills_count} skills")
    print(f"Time taken: {elapsed_time:.2f} seconds")
    print(
        f"Average time per question: {elapsed_time / max(actual_questions, 1):.2f} seconds"
    )
    print("=" * x)


if __name__ == "__main__":
    main()
