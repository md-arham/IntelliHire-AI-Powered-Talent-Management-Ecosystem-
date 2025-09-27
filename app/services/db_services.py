import uuid
from sqlalchemy.orm import Session

from app.database.models.resume_extraction_models import Skill
from app.utils.skill_question_populator import auto_populate_after_skills_added


def store_skills_from_json_with_questions(
    json_data, personal_info, db: Session, generate_questions: bool = True
):
    """
    Store skills from JSON data and optionally generate questions for newly added skills.

    Args:
        json_data (dict): JSON data containing skills information
        personal_info (PersonalInfo): User's personal info object
        db (Session): Database session
        generate_questions (bool): Whether to generate questions for newly added skills

    Returns:
        list: List of newly added skill names
    """
    skills_data = json_data.get("skills", {})
    category_mapping = {
        "programming_languages": "Programming Language",
        "tools_technologies": "Tool/Technology",
        "soft_skills": "Soft Skill",
        "relevant_courses": "Relevant Course",
    }

    # Track newly added skills for question generation
    new_skills = []

    for key, skill_str in skills_data.items():
        skill_list = [s.strip() for s in skill_str.split(",") if s.strip()]
        category = category_mapping.get(key, "Other")

        for skill in skill_list:
            existing = (
                db.query(Skill).filter_by(user=personal_info, skill_name=skill).first()
            )
            if not existing:
                skill_entry = Skill(
                    id=uuid.uuid4(),
                    user=personal_info,
                    skill_name=skill,
                    category=category,
                )
                db.add(skill_entry)
                new_skills.append(skill)

    db.commit()

    # Generate questions for new skills if requested
    if generate_questions and new_skills and personal_info.id:
        auto_populate_after_skills_added(personal_info.id, db)

    return new_skills


# Original function for backward compatibility
def store_skills_from_json(json_data, personal_info, db: Session):
    """
    Original function for backward compatibility.

    Args:
        json_data (dict): JSON data containing skills information
        personal_info (PersonalInfo): User's personal info object
        db (Session): Database session
    """
    skills_data = json_data.get("skills", {})
    category_mapping = {
        "programming_languages": "Programming Language",
        "tools_technologies": "Tool/Technology",
        "soft_skills": "Soft Skill",
        "relevant_courses": "Relevant Course",
    }

    for key, skill_str in skills_data.items():
        skill_list = [s.strip() for s in skill_str.split(",") if s.strip()]
        category = category_mapping.get(key, "Other")

        for skill in skill_list:
            existing = (
                db.query(Skill).filter_by(user=personal_info, skill_name=skill).first()
            )
            if not existing:
                skill_entry = Skill(
                    id=uuid.uuid4(),
                    user=personal_info,
                    skill_name=skill,
                    category=category,
                )
                db.add(skill_entry)

    db.commit()
