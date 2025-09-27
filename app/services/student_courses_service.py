# student_course
import random
from async_lru import alru_cache
import re
import uuid
import json
import httpx
from typing import List
from bs4 import BeautifulSoup
from fastapi import Request
from isodate import parse_duration as iso_parse_duration
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.student_course_models import StudentCourse
from app.utils.settings import settings
from app.utils.settings import ollama_async_client
from app.schemas.skills_schema import Skills
from app.utils.logger_config import logging
from app.database.models.resume_extraction_models import Skill, PersonalInfo
from app.database.models.aspiration_models import Aspiration
from app.database.models.students_models import Student
from sqlalchemy import select


# --- Utility Functions ---


def parse_duration(iso_duration: str) -> str:
    match = re.match(r"PT((\d+)H)?((\d+)M)?((\d+)S)?", iso_duration)
    if not match:
        return "Unknown"
    parts = []
    if match.group(2):
        parts.append(f"{match.group(2)} hr")
    if match.group(4):
        parts.append(f"{match.group(4)} min")
    if match.group(6):
        parts.append(f"{match.group(6)} sec")
    return " ".join(parts) if parts else "0 sec"


# --- YouTube ---


def format_youtube_course(item, video_detail):
    snippet = item["snippet"]
    video_stats = video_detail.get("statistics", {})
    video_content = video_detail.get("contentDetails", {})
    duration = parse_duration(video_content.get("duration", "PT1H"))
    thumbnail_url = (
        snippet["thumbnails"]["high"]["url"] if "thumbnails" in snippet else ""
    )
    rating = int(video_stats.get("likeCount", random.randint(100, 500)))
    return {
        "course_id": item["id"]["videoId"],
        "title": snippet["title"],
        "duration": duration,
        "platform": "YouTube",
        "course_url": f"https://www.youtube.com/watch?v={item['id']['videoId']}",
        "imageUrl": thumbnail_url,
        "image": thumbnail_url,
        "rating": rating,
    }


async def fetch_youtube_courses(query: str, request: Request) -> List[dict]:
    """
    Fetch YouTube courses matching a search query.

    Args:
        query (str): Search query for YouTube.

    Returns:
        List[dict]: List of formatted course dictionaries.
    """
    search_params = {
        "part": "snippet",
        "q": f"{query} full course",
        "type": "video",
        "maxResults": 10,
        "key": settings.YOUTUBE_API_KEY,  # Or import from settings
    }
    try:
        async_client = request.app.state.async_client
        search_res = await async_client.get(
            settings.YOUTUBE_SEARCH_URL, params=search_params
        )
    except httpx.RequestError as exc:
        logging.error(f"HTTPX error while fetching Youtube courses: {exc}")
        return []

    if search_res.status_code != 200:
        return []
    search_data = search_res.json()
    video_ids = [item["id"]["videoId"] for item in search_data.get("items", [])]
    if not video_ids:
        return []
    detail_params = {
        "part": "snippet,statistics,contentDetails",
        "id": ",".join(video_ids),
        "key": settings.YOUTUBE_API_KEY,
    }
    try:
        async_client = request.app.state.async_client
        details_res = await async_client.get(
            settings.YOUTUBE_VIDEO_URL, params=detail_params
        )
    except httpx.RequestError as exc:
        logging.error(f"HTTPX error while fetching Youtube courses: {exc}")
        return []

    if details_res.status_code != 200:
        return []
    video_details = {item["id"]: item for item in details_res.json().get("items", [])}
    formatted_courses = []
    for item in search_data["items"]:
        video_id = item["id"]["videoId"]
        video_detail = video_details.get(video_id)
        if video_detail:
            iso_duration = video_detail.get("contentDetails", {}).get(
                "duration", "PT0M"
            )
            try:
                duration_obj = iso_parse_duration(iso_duration)
                total_minutes = duration_obj.total_seconds() / 60
            except Exception as e:
                logging.warning(
                    f"Failed to parse duration {iso_duration} for video {video_id}: {e}"
                )
                total_minutes = 60
            if total_minutes >= 15:
                formatted_courses.append(format_youtube_course(item, video_detail))
    return formatted_courses


# --- Coursera ---


async def scrape_course_details_uncached(slug: str, request: Request):
    """
    Scrape course details from Coursera for a given course slug.

    Args:
        slug (str): Coursera course slug.

    Returns:
        dict: Dictionary with course title and duration.
    """
    url = f"https://www.coursera.org/learn/{slug}"
    try:
        async_client = request.app.state.async_client
        response = await async_client.get(url)
    except httpx.RequestError as exc:
        logging.error(f"HTTPX error while fetching Coursera courses: {exc}")
        return {}

    if response.status_code != 200:
        return {}
    soup = BeautifulSoup(response.text, "html.parser")
    script_tag = soup.find("script", type="application/ld+json")
    json_ld_data = {}
    if script_tag:
        try:
            json_ld_data = json.loads(script_tag.string)
        except json.JSONDecodeError as e:
            logging.warning(f"Failed to parse JSON-LD data for slug '{slug}': {e}")
            json_ld_data = {}
    title = json_ld_data.get("name", "")
    duration = "Self-paced"
    duration_tag = soup.find(
        "div", string=re.compile(r"hours to complete", re.IGNORECASE)
    )
    if duration_tag:
        duration = duration_tag.get_text(strip=True)
    return {
        "title": title,
        "duration": duration,
    }


@alru_cache(maxsize=100)
async def scrape_course_details(slug: str):
    """
    Cached wrapper for scraping Coursera course details.

    Args:
        slug (str): Coursera course slug.

    Returns:
        dict: Dictionary with course title and duration.
    """
    return await scrape_course_details_uncached(slug)


async def format_course_data(course):
    """
    Format Coursera course data into a standardized dictionary.

    Args:
        course (dict): Raw course data from Coursera API.

    Returns:
        dict: Formatted course dictionary.
    """
    slug = course.get("slug", "")
    course_id = course.get("id", str(uuid.uuid4()))
    course_url = f"https://www.coursera.org/learn/{slug}" if slug else ""
    scraped = await scrape_course_details(slug)
    return {
        "course_id": f"course-{course_id}",
        "title": scraped.get("title", course.get("name", "Untitled")),
        "duration": scraped.get("duration", "Self-paced"),
        "platform": "Coursera",
        "course_url": course_url,
        "imageUrl": scraped.get("imageUrl", ""),
        "image": scraped.get("image", ""),
        "rating": scraped.get("rating", 4.5),
    }


async def fetch_coursera_courses(query: str, request: Request) -> List[dict]:
    """
    Fetch Coursera courses matching a search query.

    Args:
        query (str): Search query for Coursera.

    Returns:
        List[dict]: List of formatted course dictionaries.
    """
    url = f"{settings.COURSERA_BASE_URL}?q=search&query={query}&limit=20"
    try:
        async_client = request.app.state.async_client
        res = await async_client.get(url)
    except httpx.RequestError as exc:
        logging.error(f"HTTPX error while fetching Coursera courses: {exc}")
        return []
    if res.status_code != 200:
        return []
    data = res.json()
    courses = []
    for course in data.get("elements", [])[:5]:
        formatted = await format_course_data(course)
        if (
            formatted.get("title") and formatted.get("title").strip()
        ):  # Only add if title exists and is not empty
            courses.append(formatted)
    return courses


# --- Aggregate Fetch ---


async def fetch_courses(queries: List[str]) -> List[dict]:
    """
    Fetch courses from YouTube and Coursera for a list of queries.

    Args:
        queries (List[str]): List of search queries.

    Returns:
        List[dict]: Combined list of formatted course dictionaries.
    """
    youtube_courses = []
    coursera_courses = []
    for query in queries:
        youtube_courses.extend(await fetch_youtube_courses(query))
        coursera_courses.extend(await fetch_coursera_courses(query))
    return youtube_courses + coursera_courses


async def recommend_courses(skillset: List[str], aspiration: List[str]) -> List[dict]:
    """
    Recommend courses based on a skillset and aspirations.

    Args:
        skillset (List[str]): List of user's current skills.
        aspiration (List[str]): List of user's aspirations.

    Returns:
        List[dict]: List of recommended courses.
    """
    all_courses = await fetch_courses(aspiration)
    simplified = []
    for course in all_courses:
        simplified.append(
            {
                "course_id": course.get("course_id") or course.get("id"),
                "title": course.get("title"),
                "duration": course.get("duration"),
                "platform": course.get("platform"),
                "course_url": course.get("course_url"),
                "imageUrl": course.get("imageUrl"),
                "image": course.get("image"),
                "rating": course.get("rating"),
            }
        )
    return simplified  # returns list of courses for the given skillset and aspiration


async def create_student_courses(
    db: AsyncSession, user_id: uuid.UUID, roadmap_id: uuid.UUID = None
) -> List[StudentCourse]:
    # 1. Execute the query
    result = await db.execute(select(Student).filter(Student.user_id == user_id))
    student = result.scalars().first()
    if not student:
        raise ValueError(f"Student not found for user_id: {user_id}")

    student_id = student.student_id

    # Get user's existing skills
    user_skills = await get_user_skills(db, user_id)

    # Get user's aspirations
    aspirations = await get_user_aspirations(db, student_id)

    if not aspirations:
        logging.warning(f"No aspirations found for student {student_id}")
        return []

    created_courses = []

    # Process each aspiration separately
    for aspiration in aspirations:
        logging.info(f"Processing aspiration: {aspiration}")

        # Determine skill gap for this specific aspiration
        # We pass a list with just this aspiration to focus on its requirements
        skill_gaps = determine_skill_gap(user_skills, [aspiration])
        logging.info("skill_gaps", skill_gaps)

        # Get recommended courses for this aspiration
        raw_result = recommend_courses(user_skills, skill_gaps)
        logging.info("raw_result", raw_result)

        # Parse results
        if isinstance(raw_result, str):
            cleaned_result = re.sub(r"[\x00-\x1f\x7f]", "", raw_result)
            try:
                parsed_result = json.loads(cleaned_result)
                courses_data = parsed_result.get("courses", parsed_result)
            except json.JSONDecodeError:
                logging.error(
                    f"Failed to parse course recommendations for {aspiration}"
                )
                courses_data = []
        else:
            courses_data = raw_result

        # Create course entries for this aspiration
        for course in courses_data:
            course_id = uuid.uuid4()
            entry = StudentCourse(
                course_id=course_id,
                student_id=student_id,
                roadmap_id=roadmap_id,
                status="Not Started",
                progress_percent=0,
                last_accessed=None,
                title=course.get("title"),
                level=course.get("level", "Beginner"),
                duration=course.get("duration"),
                url=course.get("course_url") or course.get("courseUrl"),
                rating=course.get("rating"),
                imageUrl=course.get("imageUrl") or "",
                image=course.get("image") or "",
                aspiration_name=aspiration,  # Set aspiration name for each course
            )
            db.add(entry)
            created_courses.append(entry)

    await db.commit()
    return created_courses


async def get_user_skills(db: AsyncSession, student_id: uuid.UUID) -> List[str]:
    """Fetch user's skills from the database by following the relationship chain"""
    # Then get the personal_info record using student_id
    result = await db.execute(
        select(PersonalInfo).filter(PersonalInfo.student_id == student_id)
    )
    personal_info = result.scalars().first()
    if not personal_info:
        return []

    # Finally get skills using personal_info.id which matches the user_id in Skills table
    result = await db.execute(select(Skill).filter(Skill.user_id == personal_info.id))
    skills = result.scalars().all()

    return [skill.skill_name for skill in skills]


async def get_user_aspirations(db: AsyncSession, student_id: uuid.UUID) -> List[str]:
    """Fetch user's aspirations from the database"""
    """Fetch user's aspirations from the database"""
    result = await db.execute(
        select(Aspiration).filter(Aspiration.student_id == student_id)
    )
    aspirations = result.scalars().all()
    return [aspiration.aspiration_text for aspiration in aspirations]


async def determine_skill_gap(
    existing_skills: List[str], aspirations: List[str]
) -> List[str]:
    """
    Determine the skill gap between existing skills and aspirations using an LLM.

    Args:
        existing_skills (List[str]): List of user's current skills.
        aspirations (List[str]): List of aspirations.

    Returns:
        List[str]: List of top skills needed to achieve the aspirations.
    """

    if not aspirations:
        return []

    combined_aspirations = ", ".join(aspirations)

    prompt = f"""
    You are an expert career advisor. Given a person's existing skills and career aspirations,
    identify the top 5 skills they need to acquire to achieve their goals.
    
    Existing skills: {", ".join(existing_skills) if existing_skills else "None"}
    Career aspirations: {combined_aspirations}
    
    Output a Python list of maximum 5 skills that represent the skill gap.
    """

    response = await ollama_async_client.chat(
        model=settings.OLLAMA_MODEL,
        messages=[{"role": "system", "content": prompt}],
        format=Skills.model_json_schema(),  # Pass the schema as JSON
    )
    try:
        skill_gap = Skills.model_validate_json(response.message.content)
        return skill_gap.skills
    except Exception as e:
        logging.error(f"Failed to parse LLM response: {e}")
        return []
