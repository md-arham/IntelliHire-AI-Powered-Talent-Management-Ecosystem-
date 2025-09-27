
import json
import random
import re
import uuid
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from bs4 import BeautifulSoup
from async_lru import alru_cache
from fastapi import HTTPException, Request
from isodate import parse_duration as iso_parse_duration
from sqlalchemy import select
from app.utils.settings import settings
from app.utils.logger_config import logging
from app.schemas.courses_schema import (
    CourseItem,
    StudentCourseFetchRequest
)
from app.database.models.student_course_models import StudentCourse
from app.database.models.students_models import Student
from app.services.student_courses_service import parse_duration
from collections import defaultdict

def guess_category(title: str, description: str, topics: List[str]) -> str:
    combined_text = f"{title}".lower()
    categories = {
        "Technology": [
            "python",
            "java",
            "javascript",
            "react",
            "node",
            "flutter",
            "programming",
            "development",
            "web",
            "backend",
            "frontend",
            "devops",
            "cloud",
            "aws",
            "azure",
            "linux",
            "software",
            "database",
            "sql",
            "docker",
            "kubernetes",
            "ai",
            "ml",
            "machine learning",
            "data science",
            "deep learning",
            "cybersecurity",
            "blockchain",
        ],
        "Marketing": [
            "marketing",
            "seo",
            "digital marketing",
            "branding",
            "content",
            "ads",
            "advertising",
            "social media",
            "email marketing",
            "influencer",
            "copywriting",
            "campaign",
            "google ads",
            "facebook ads",
            "growth hacking",
            "conversion",
            "funnel",
            "lead generation",
        ],
        "Finance": [
            "finance",
            "investment",
            "stock",
            "trading",
            "cryptocurrency",
            "accounting",
            "budgeting",
            "bookkeeping",
            "financial",
            "valuation",
            "tax",
            "income",
            "expenses",
            "portfolio",
            "economics",
            "wealth",
            "personal finance",
            "funding",
            "risk",
            "audit",
        ],
        "Design": [
            "design",
            "ui",
            "ux",
            "graphic",
            "photoshop",
            "illustrator",
            "figma",
            "adobe",
            "canva",
            "visual",
            "typography",
            "product design",
        ],
        "Human Resources": [
            "human resources",
            "hr",
            "recruitment",
            "hiring",
            "interview",
            "onboarding",
            "employee",
            "talent",
            "performance",
            "benefits",
            "workforce",
            "labor law",
            "training",
            "organizational behavior",
            "diversity",
            "people management",
        ],
        "Operations": [
            "operations",
            "supply chain",
            "logistics",
            "inventory",
            "process",
            "workflow",
            "project management",
            "scrum",
            "agile",
            "kanban",
            "lean",
            "quality",
            "efficiency",
            "manufacturing",
            "production",
            "strategy",
            "delivery",
        ],
    }
    for category, keywords in categories.items():
        if any(re.search(rf"\b{re.escape(keyword)}\b", combined_text) for keyword in keywords):
            return category
    return "Other"





def extract_hashtags(description: str) -> List[str]:
    return re.findall(r"#\w+", description)


def format_youtube_course(item, video_detail):
    snippet = item["snippet"]
    video_stats = video_detail.get("statistics", {})
    video_content = video_detail.get("contentDetails", {})

    title = snippet["title"]
    description = snippet.get("description", "Learn something amazing!")
    channel_title = snippet.get("channelTitle", "Top Instructor")
    thumbnail_url = (
        snippet["thumbnails"]["high"]["url"] if "thumbnails" in snippet else ""
    )
    duration = parse_duration(video_content.get("duration", "PT1H"))
    topics = extract_hashtags(description)
    rating = int(video_stats.get("likeCount", random.randint(100, 500)))
    enrolled = int(video_stats.get("viewCount", random.randint(1000, 100000)))

    return {
        "id": item["id"]["videoId"],
        "title": title,
        "description": description,
        "instructor": channel_title,
        "category": guess_category(title, description, topics),
        "duration": duration,
        "level": "All Levels",
        "imageUrl": thumbnail_url,
        "image": thumbnail_url,
        "courseUrl": f"https://www.youtube.com/watch?v={item['id']['videoId']}",
        "rating": rating,
        "enrolled": enrolled,
        "topics": topics,
        "platform": "YouTube",
        "pricingType": "Free",
    }




async def scrape_course_details_uncached(slug: str, request:Request):
    """
    Scrape Coursera course details by slug (uncached version).

    Args:
        slug (str): Coursera course slug.

    Returns:
        dict: Scraped course data.
    """
    url = f"https://www.coursera.org/learn/{slug}"
    
    
    async_client = request.app.state.async_client
    response = await async_client.get(url)
    if response.status_code != 200:
        return {}
    soup = BeautifulSoup(response.text, "html.parser")
    json_ld_data = {}
    script_tag = soup.find("script", type="application/ld+json")
    if script_tag:
        try:
            json_ld_data = json.loads(script_tag.string)
        except json.JSONDecodeError as e:
            logging.warning(f"Failed to parse JSON-LD data for slug '{slug}': {e}")
            json_ld_data = {}
    instructor = "Instructor: TBD"
    instructor_tag = soup.find("span", class_="instructor-name")
    if instructor_tag:
        instructor = instructor_tag.get_text(strip=True)
    else:
        instructors_section = soup.find_all("a", href=re.compile(r"^/instructor/"))
        if instructors_section:
            instructor = instructors_section[0].get_text(strip=True)
    duration = "Self-paced"
    duration_tag = soup.find(
        "div", string=re.compile(r"hours to complete", re.IGNORECASE)
    )
    if duration_tag:
        duration = duration_tag.get_text(strip=True)
    enrolled = random.randint(500, 5000)
    enrolled_tag = soup.find(
        "div", string=re.compile(r"already enrolled", re.IGNORECASE)
    )
    if enrolled_tag:
        match = re.search(r"([\d,]+)", enrolled_tag.text)
        if match:
            enrolled = int(match.group(1).replace(",", ""))
    image = json_ld_data.get("image", "")
    title = json_ld_data.get("name", "")
    description = json_ld_data.get("description", "No description provided.")
    if not title or not description:
        return {}
    return {
        "title": title,
        "description": description,
        "instructor": instructor,
        "image": image,
        "imageUrl": image,
        "level": json_ld_data.get("educationalLevel", "Beginner"),
        "topics": json_ld_data.get("about", []),
        "enrolled": enrolled,
        "rating": round(
            float(json_ld_data.get("aggregateRating", {}).get("ratingValue", 4.5)), 1
        ),
        "duration": duration,
    }


@alru_cache(maxsize=100)
async def scrape_course_details(slug: str):
    """
    Retrieve Coursera course details using cache if available.

    Args:
        slug (str): Coursera course slug.

    Returns:
        dict: Cached or freshly scraped course details.
    """
    return await scrape_course_details_uncached(slug)


async def format_course_data(course):
    """
    Format raw Coursera API course data into a structured dictionary.

    Args:
        course (dict): Raw course data from Coursera API.

    Returns:
        dict: Structured course data suitable for the frontend.
    """
    slug = course.get("slug", "")
    course_id = course.get("id", str(uuid.uuid4()))
    course_url = f"https://www.coursera.org/learn/{slug}" if slug else ""
    scraped = await scrape_course_details(slug)
    return {
        "id": f"course-{course_id}",
        "title": scraped.get("title", course.get("name", "Untitled")),
        "description": scraped.get("description", ""),
        "instructor": scraped.get("instructor", "Instructor: TBD"),
        "category": guess_category(
            scraped.get("title", course.get("name", "")),
            scraped.get("description", ""),
            scraped.get("topics", []),
        ),
        "duration": scraped.get("duration", "Self-paced"),
        "level": scraped.get("level", "Beginner"),
        "imageUrl": scraped.get("imageUrl", ""),
        "image": scraped.get("image", ""),
        "courseUrl": course_url,
        "rating": scraped.get("rating", 4.5),
        "enrolled": scraped.get("enrolled", random.randint(500, 5000)),
        "topics": scraped.get("topics", []),
        "platform": "Coursera",
        "pricingType": "Paid",
    }


async def fetch_all_youtube_courses(query: str, request: Request) -> List[dict]:
    """
    Fetch and format a list of YouTube courses based on a query.

    Args:
        query (str): Search query string.

    Returns:
        List[dict]: List of formatted YouTube course data.
    """
    search_params = {
        "part": "snippet",
        "q": f"{query} full course",
        "type": "video",
        "maxResults": 25,
        "key": settings.YOUTUBE_API_KEY,
    }

    async_client = request.app.state.async_client
    search_res = await async_client.get(settings.YOUTUBE_SEARCH_URL, params=search_params)
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
    async_client = request.app.state.async_client
    details_res = await async_client.get(settings.YOUTUBE_VIDEO_URL, params=detail_params)
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
                logging.warning(f"Failed to parse duration {iso_duration} for video {video_id}: {e}")
                total_minutes = 60
            if total_minutes >= 15:
                formatted_courses.append(format_youtube_course(item, video_detail))
    return formatted_courses


async def fetch_all_coursera_courses(query: str, request:Request) -> List[dict]:
    """
    Fetch and format a list of Coursera courses based on a query.

    Args:
        query (str): Search query string.

    Returns:
        List[dict]: List of formatted Coursera course data.
    """
    url = f"{settings.COURSERA_BASE_URL}?q=search&query={query}&limit=20"
    async_client = request.app.state.async_client
    
    res = await async_client.get(url)
    if res.status_code != 200:
        return []
    data = res.json()
    courses = [format_course_data(course) for course in data.get("elements", [])[:20]]
    return courses



async def group_courses_by_aspirations(payload: StudentCourseFetchRequest, db :AsyncSession):
    # Fetch student_id from user_id
    result = await db.execute(
        select(Student).filter(Student.user_id == payload.user_id)
    )
    student = result.scalars().first()
    if not student:
        raise HTTPException(
            status_code=404, detail="Student not found for this user_id."
        )
    
    result = await db.execute(
        select(StudentCourse).filter(
            StudentCourse.student_id == student.student_id
        )
    )
    student_courses = result.scalars().all()
    
    
    if not student_courses:
        raise HTTPException(
            status_code=404, detail="No courses found for this student."
        )
    
    # Group courses by aspiration
    grouped_courses = defaultdict(list)
    for course in student_courses:
        # Create a CourseItem object for each course
        course_item = CourseItem(
            course_id=course.course_id,
            title=course.title,
            level=course.level,
            duration=course.duration,
            url=course.url,
            status=course.status,
            progress_percent=course.progress_percent,
            rating=course.rating,
            imageUrl=course.imageUrl,
            image=course.image
        )
        # Group by aspiration_name
        grouped_courses[course.aspiration_name].append(course_item)
    
    # Returning a dictionary with aspiration names as key and lists of courses as values
    return {"courses": dict(grouped_courses)}
