import asyncio
import uuid
from typing import List

from fastapi import HTTPException

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database.models.aspiration_models import Aspiration
from app.database.models.roadmaps_models import Roadmaps
from app.schemas.roadmap_schema import Roadmap
from app.utils.settings import ollama_async_client, settings
from app.database.models.resume_extraction_models import Skill, Projects, Certification

ROADMAP_SYSTEM_PROMPT = """
You are an expert career advisor. Your task is to generate a structured learning roadmap for someone who wants to become a certain job role or has an aspiration.

Return your answer as **strictly valid, raw, and indented JSON**, formatted exactly according to this schema:

{{
  "roadmap": {{
    "title": string,
    "timeline": string,
    "phases": [
      {{
        "name": string,  // Must follow the format: "Phase X: Name"
        "duration": string,
        "objective": string,
        "skills_needed": [string],
        "tools": [string],
        "courses": [
          {{
            "title": string,
            "provider": string,
            "duration": string
          }}
        ],
        "projects": [string]
      }}
    ],
    "tips": [string]
  }}
}}

Strict Output Rules:
- Return only the JSON. No markdown, no explanation, no quotes around the JSON.
- All arrays must be non-empty and fully filled out.
- `phases` must contain **exactly 4 items** with names: 
  - "Phase 1: Foundation"
  - "Phase 2: Intermediate"
  - "Phase 3: Advanced"
  - "Phase 4: Mastery"
- Do **not** add any extra phases, tips-as-phases, or final project sections.
- The `tips` field must contain 2 to 3 helpful, realistic tips — not nested under `phases`.
- Do not repeat or add fields outside of the given schema.
- Ensure the JSON is valid and parsable by a strict JSON parser.
"""


ROADMAP_USER_PROMPT = """
Now generate the roadmap for the role: "{job_role}"
"""


ROADMAP_SYSTEM_PROMPT_PERSONALIZED = """
You are an expert career advisor. Your task is to generate a structured learning roadmap for someone who wants to become a become a certain job role or has an aspiration.
Take in account the skills of the person which will be given in the prompt, and make a roadmap personalized to them. Take in account the projects they have and skills they already possess. Deduce skill level and knowledge from the experience and personal projects.
Return your answer as **strictly valid, raw, and indented JSON**, formatted exactly according to this schema:

{{
  "roadmap": {{
    "title": string,
    "timeline": string,
    "phases": [
      {{
        "name": string,  // Must follow the format: "Phase X: Name"
        "duration": string,
        "objective": string,
        "skills_needed": [string],
        "tools": [string],
        "courses": [
          {{
            "title": string,
            "provider": string,
            "duration": string
          }}
        ],
        "projects": [string]
      }}
    ],
    "tips": [string]
  }}
}}

Strict Output Rules:
- All arrays must be non-empty and fully filled out.
- `phases` must contain **exactly 4 items** with names: 
  - "Phase 1: Foundation"
  - "Phase 2: Intermediate"
  - "Phase 3: Advanced"
  - "Phase 4: Mastery"
- Do **not** add any extra phases, tips-as-phases, or final project sections.
- The `tips` field must contain 2 to 3 helpful, realistic tips — not nested under `phases`.
- Do not repeat or add fields outside of the given schema.
- Ensure the JSON is valid and parsable by a strict JSON parser.
"""

ROADMAP_USER_PROMPT_PERSONALIZED = """
Now generate the roadmap for the role: "{job_role}", given following users data:
Skills: "{skills}"
Projects: "{projects}"
Certifications: "{certificates}"
"""

async def get_personal_data(db: AsyncSession, student_id: str):
    result = await db.execute(
        select(Projects).where(Projects.user_id == student_id)
    )
    projects = result.scalars().all()

    result = await db.execute(
        select(Skill).where(Skill.user_id == student_id)
    )
    skills = result.scalars().all()

    result = await db.execute(
        select(Certification).where(Certification.user_id == student_id)
    )
    certificates = result.scalars().all()

    projects_formatted = "\n".join(project.title + "\n" + project.details for project in projects)
    skills_formatted = " ".join(skill.skill_name for skill in skills)
    certificates_formatted = " ".join(certificate.certification_name for certificate in certificates)

    return projects_formatted, skills_formatted, certificates_formatted


async def generate_roadmaps_personalized_async(db: AsyncSession, student_id: str, aspiration):
    projects, skills, certificates = await get_personal_data(db, student_id)
    messages = [
      {"role": "system", "content": ROADMAP_SYSTEM_PROMPT_PERSONALIZED},
      {"role": "user", "content": ROADMAP_USER_PROMPT_PERSONALIZED.format(job_role=aspiration, skills=skills, projects=projects, certificates=certificates)}
    ]
    response = await ollama_async_client.chat(
      model=settings.OLLAMA_MODEL,
      messages=messages,
      format=Roadmap.model_json_schema()
    )

    roadmap_content = Roadmap.model_validate_json(response.message.content)

    return roadmap_content.model_dump(), aspiration

async def generate_roadmap_async(aspiration: str):
    messages = [
        {
            "role": "system", "content": ROADMAP_SYSTEM_PROMPT,
            "role": "user", "content": ROADMAP_USER_PROMPT.format(job_role=aspiration)
        }
    ]
    response = await ollama_async_client.chat(
        model=settings.OLLAMA_MODEL,
        messages=messages,
        format=Roadmap.model_json_schema(),
    )

    roadmap_content = Roadmap.model_validate_json(response.message.content)

    return roadmap_content.model_dump(), aspiration


async def generate_roadmaps_personalized(db: AsyncSession, student_id: str, aspirations: List[str]):
    roadmaps = [
        asyncio.create_task(generate_roadmaps_personalized_async(db, student_id, aspiration))
        for aspiration in aspirations
    ]
    for task in asyncio.as_completed(roadmaps):
        yield await task

async def generate_roadmaps_async(aspirations: List[str]):
    roadmaps = [
        asyncio.create_task(generate_roadmap_async(aspiration))
        for aspiration in aspirations
    ]
    for task in asyncio.as_completed(roadmaps):
        yield await task


async def store_aspirations(
    db: AsyncSession, student_id: str, aspirations: List[str]
) -> List[Aspiration]:
    if len(aspirations) > 3:
        raise HTTPException(
            status_code=400, detail="Maximum of 3 aspirations allowed per student."
        )

    created_aspirations = [
        Aspiration(
            student_id=student_id,
            aspiration_id=uuid.uuid4(),
            aspiration_text=aspiration,
        )
        for aspiration in aspirations
    ]

    db.add_all(created_aspirations)

    await db.commit()

    for aspiration in created_aspirations:
      await db.refresh(aspiration)

    return created_aspirations


async def store_roadmap(
    db: AsyncSession, student_id: str, aspiration: str, roadmap: Roadmap
) -> Roadmaps:
    roadmap = Roadmaps(
        student_id=student_id, roadmap_id=uuid.uuid4(), role=aspiration, data=roadmap
    )
    db.add(roadmap)
    await db.commit()
    await db.refresh(roadmap)
    return roadmap
