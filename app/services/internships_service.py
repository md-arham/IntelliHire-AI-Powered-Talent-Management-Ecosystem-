from math import ceil
from app.database.models.bookmark_models import Bookmark
from app.database.models.students_models import Student
from app.schemas.job_postings_schema import PaginatedInternshipResponse
from fastapi import HTTPException, status
from itertools import zip_longest
import uuid
from datetime import datetime, date
from typing import Any, Dict, List, Optional
import json
from app.database.models.enums_models import InternshipType, JobType
from app.schemas.internships_schema import InternshipFilterRequest
import httpx
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import update

from app.database.models.job_postings_models import (
    JobCategoryType,
    JobOriginType,
    JobPosting,
)
from app.utils.logger_config import logger
from app.utils.settings import settings
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, func

"""
InternshipScraper handles fetching and preprocessing internship listings
from a RapidAPI endpoint. Configurable via constructor for API details,
timeout, and field mappings.
"""


class InternshipScraper:

    """
    The below variables might be misinterpreted as global variables.
    But these are being used to preprocess the internships response form the RAPID API.
    """

    # Default mapping of API fields to internal schema keys
    DEFAULT_KEY_MAP: Dict[str, str] = {
        "date_validthrough": "applicationDeadline",
        "date_posted": "postedDate",
        "organization": "company",
        "linkedin_org_description": "company_description",
        "organization_url": "company_url",
        "linkedin_org_locations": "address",
        "organization_logo": "companyLogo",
        "remote_derived": "isRemote",
        "linkedin_org_size": "company_size",
        "linkedin_org_foundeddate": "company_founded_date",
        "linkedin_org_headquarters": "company_headquarters",
        "description_text": "description",
        "ai_experience_level": "experience_level",
        "ai_work_arrangement": "work_type",
        "ai_key_skills": "skills",
        "ai_core_responsibilities": "responsibilities",
        "ai_requirements_summary": "requirements",
    }

    # Default list of keys to drop from raw records
    DEFAULT_POP_KEYS: List[str] = [
        "locations_raw",
        "location_type",
        "location_requirements_raw",
        "locations_derived",
        "timezones_derived",
        "lats_derived",
        "lngs_derived",
        "linkedin_org_employees",
        "linkedin_org_url",
        "linkedin_org_slogan",
        "linkedin_org_industry",
        "linkedin_org_followers",
        "linkedin_org_type",
        "linkedin_org_specialties",
        "linkedin_org_recruitment_agency_derived",
        "seniority",
        "directapply",
        "linkedin_org_slug",
        "ai_visa_sponsorship",
        "ai_salary_unittext",
        "ai_salary_minvalue",
        "ai_salary_maxvalue",
        "ai_salary_currency",
        "ai_remote_location",
        "ai_work_arrangement_office_days",
        "ai_remote_location_derived", 
        "ai_hiring_manager_name",
        "ai_working_hours", 
        "ai_job_language", 
        "recruiter_url"
    ]

    """
    Constructor
    @param api_url Endpoint URL for fetching listings
    @param api_key RapidAPI authentication key
    @param api_host RapidAPI host header value
    @param timeout Request timeout in seconds
    @param key_map Optional custom field rename mapping
    @param pop_keys Optional list of fields to drop from records
    """

    def __init__(
        self,
        api_url: str = settings.RAPID_API_URL,
        api_key: str = settings.RAPID_API_KEY_INTERNSHIPS,
        api_host: str = settings.RAPID_API_HOST,
        timeout: float = 60.0,
        key_map: Optional[Dict[str, str]] = None,
        pop_keys: Optional[List[str]] = None,
    ) -> None:
        self.api_url = api_url
        self.headers = {"x-rapidapi-key": api_key, "x-rapidapi-host": api_host}
        self._key_map = key_map or self.DEFAULT_KEY_MAP
        self._pop_keys = pop_keys or self.DEFAULT_POP_KEYS
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(timeout))

    """
    Rename and filter raw record keys.
    @param record Single internship record from API response
    @return New dict with renamed and filtered keys
    """

    async def _map_keys(self, record: Dict[str, Any]) -> Dict[str, Any]:
        mapped = {self._key_map.get(k, k): v for k, v in record.items()}
        return mapped

    """
    Convert ISO date strings to date objects.
    @param record Internship dict containing potential date strings
    """

    def _format_dates(self, record: Dict[str, Any]) -> None:
        for field in ("postedDate", "applicationDeadline"):
            val = record.get(field)
            if isinstance(val, str):
                try:
                    record[field] = datetime.fromisoformat(val)
                except ValueError:
                    logger.warning(f"Invalid date format for {field}: {val}")
                    record[field] = None

    """
    Extract structured and displayable location fields.
    @param record Internship dict with cities_derived, regions_derived, countries_derived
    """

    def _extract_locations(self, record: Dict[str, Any]) -> None:
        cities = record.pop("cities_derived", []) or []
        regions = record.pop("regions_derived", []) or []
        countries = record.pop("countries_derived", []) or []
        record["locations"] = {
            "cities": cities,
            "regions": regions,
            "countries": countries,
        }
        record["location"] = ", ".join(
            f"{c or '--'}, {r or '--'}, {ct or '--'}"
            for c, r, ct in zip_longest(cities, regions, countries)
        )
        record["city"] = ", ".join(cities)
        record["country"] = ", ".join(countries)

    """
    Build stipend information from raw salary fields.
    @param record Internship dict with ai_salary_* fields
    """

    def _build_stipend(self, record: Dict[str, Any]) -> None:
        record["stipend"] = {
            "amount": record.get("ai_salary_value"),
            "minAmount": record.get("ai_salary_minvalue"),
            "maxAmount": record.get("ai_salary_maxvalue"),
            "currency": record.get("ai_salary_currency"),
            "payPeriod": record.get("ai_salary_unittext"),
        }


    """
    Run full preprocessing pipeline on raw API data.
    Steps: _map_keys, _format_dates, _extract_locations, _build_stipend, attach metadata
    @param raw_data List of raw internship dicts
    @param role Role label to add to each record
    @param category Category label to add to each record
    @return List of cleaned internship dicts
    """

    async def preprocess_response(
        self,
        raw_data: List[Dict[str, Any]],
        role: str,
        category: str,
    ) -> List[Dict[str, Any]]:
        processed: List[Dict[str, Any]] = []
        for item in raw_data:
            record = await self._map_keys(item)
            self._format_dates(record)
            self._extract_locations(record)
            self._build_stipend(record)
            record.update(
                {
                    "startDate": None,
                    "duration": None,
                    "employerId": None,
                    "role": role,
                    "category": category,
                }
            )
            record.update(
                {
                    "compensation": (
                        "Paid" if record.get("stipend",{}).get("amount") or 
                        record.get("stipend",{}).get("minAmount") or 
                        record.get("stipend",{}).get("maxAmount") or 
                        record.get("stipend",{}).get("payPeriod") 
                        else "Not Specified"
                    )
                }
            )
            processed.append({k: v for k, v in record.items() if k not in self._pop_keys})
        return processed

    """
    Fetch listings from API, validate, and preprocess.
    @param query_params HTTP GET query parameters
    @param role Role label for metadata
    @param category Category label for metadata
    @return List of preprocessed internship records
    @throws httpx.HTTPError on request failure
    """

    async def fetch_job_listings(
        self,
        query_params: Dict[str, Any],
        role: str,
        category: str,
    ) -> List[Dict[str, Any]]:
        try:
            response = await self.client.get(
                self.api_url, headers=self.headers, params=query_params
            )
            response.raise_for_status()
            data = response.json()
            return await self.preprocess_response(data, role, category)
        except httpx.HTTPError as e:
            logger.error(f"Error fetching job listings : {e}")
            raise
    
    """
    Gracefully closes the underlying HTTP client session.

    This should be called after all job fetching operations are complete
    to ensure that connections are properly released and resources are cleaned up.
    """

    async def close(self):
        await self.client.aclose()



"""
InternshipRepository manages bulk database operations for Internship ORM.
"""


class InternshipRepository:
    """
    Constructor
    @param db_session Active SQLAlchemy Session
    """

    def __init__(self, db_session: AsyncSession) -> None:
        self.db = db_session

    """
    Serialize date or datetime objects to ISO 8601 string format for JSON compatibility.
    """

    def serialize_for_json(self, obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return obj
    

    """
    Safely parse a datetime string to a datetime object.

    Args:
        value (Any): The input value to parse. Can be a datetime object, 
                     an ISO 8601 datetime string, or None.

    Returns:
        Optional[datetime]: A datetime object if parsing succeeds, or None 
                            if the input is invalid or unparsable.

    Notes:
        - If the input is already a datetime object, it is returned as-is.
        - If the input is a valid ISO 8601 string (e.g., "2025-07-07T04:06:11"), 
          it is parsed into a datetime object.
        - If parsing fails, a warning is logged and None is returned.
    """
    def parse_datetime(self, value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value.replace(tzinfo=None) if value.tzinfo else value
        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value)
                return dt.replace(tzinfo=None) if dt.tzinfo else dt
            except ValueError:
                logger.warning(f"Invalid datetime format: {value}")
        return None

    """
    Convert dict records to ORM instances and perform bulk insert.
    @param records List of preprocessed internship dicts
    """

    async def insert_bulk(self, records: List[Dict[str, Any]]) -> None:
        internships: List[JobPosting] = []
        for item in records:
            try:
                internships.append(
                    JobPosting(
                        job_id=uuid.uuid4(),
                        employer_id=None,
                        job_origin=JobOriginType.EXTERNAL,
                        job_category_type=JobCategoryType.INTERNSHIP,
                        company_name=item.get("company") or "Not Specified",
                        title=item.get("title") or "Untitled Internship",
                        description=item.get("description") or "Not Specified.",
                        location=item.get("location") or "Not Specified",
                        internship_type=(
                            InternshipType.Remote
                            if "Remote" in (item.get("work_type") or "")
                            else InternshipType.Onsite
                            if (item.get("work_type") or "") == "On-site"
                            else InternshipType.Hybrid
                        ),
                        stipend=str(item.get("stipend", {}).get("amount")) or "Not Specified",
                        category=item.get("category") or "Not Specified",
                        role=item.get("role") or "Not Specified",
                        required_skills=item.get("skills") or [],
                        responsibilities=item.get("responsibilities") or "Not Specified",
                        requirements=item.get("requirements") or "Not Specified",
                        application_deadline=(
                            item.get("applicationDeadline").date()
                            if isinstance(item.get("applicationDeadline"), datetime)
                            else None
                        ),
                        posted_at=self.parse_datetime(item.get("postedDate")),
                        job_type=JobType.Internship,
                        min_experience=str(item.get("experience_level") or "Not Specified"),
                        salary_range=(
                            str(item.get("stipend",{}).get("minAmount")
                                or "Not Specified")
                            + " - " + 
                            str(item.get("stipend",{}).get("maxAmount")
                                  or "Not Specified")
                        ),
                        additional_info=json.loads(
                            json.dumps(item, default=self.serialize_for_json)
                        ),
                    )
                )
            except SQLAlchemyError:
                logger.error("Failed to map record to Internship: %s", item)

        try:
            self.db.add_all(internships)
            await self.db.commit()
        except SQLAlchemyError:
            await self.db.rollback()
            logger.error("Failed to commit internships to database.")

    async def deactivate_expired_internships_service(self) -> str:
        """
        Marks all active internships with an application deadline before today as inactive.

        Returns:
            str: Message describing how many internships were deactivated.
        """
        today = date.today()
        try:
            stmt = (
                update(JobPosting)
                .where(
                    JobPosting.application_deadline < today,
                    JobPosting.is_active.is_(True),
                )
                .values(is_active=False)
                .execution_options(synchronize_session=False)
            )

            result = await self.db.execute(stmt)
            await self.db.commit()
            updated_count = result.rowcount or 0

            logger.info(f"Deactivated {updated_count} expired internships.")
            if updated_count == 0:
                return "No expired internships needed deactivation."
            return f"Deactivated {updated_count} expired internships."

        except Exception as e:
            await self.db.rollback()
            logger.error("Database error during internship deactivation.")
            raise RuntimeError(f"Failed to deactivate expired internships: {str(e)}")

async def refactor_response(data: List[JobPosting]) -> List[JobPosting]:
    for job in data:
        add_info = {
            "posting_url": job.additional_info.get("url") if job.additional_info else None,
            "source": job.additional_info.get("source") if job.additional_info else None,
            "stipend": {
                "amount": job.stipend,
                "payPeriod": job.additional_info.get("stipend", {}).get("payPeriod") if job.additional_info else None,
                "currency": job.additional_info.get("stipend", {}).get("currency") if job.additional_info else None,
            },
            "company_logo": job.additional_info.get("companyLogo") if job.additional_info else None,
            "requirements": job.requirements,
            "responsibilities": job.responsibilities,
            "job_origin": job.job_origin.value,
            "job_category_type": job.job_category_type.value,
            "compensation": job.additional_info.get("compensation") if job.additional_info else None,
            "company_url": job.additional_info.get("company_url") if job.additional_info else None,
            "company_description": job.additional_info.get("company_description") if job.additional_info else None,
        }
        job.additional_info = add_info
    return data

async def get_paginated_external_internships(request: InternshipFilterRequest, db: AsyncSession):
    student_id = None
    if request.user_id:
        try:
            student_result = await db.execute(
                select(Student).filter(Student.user_id == request.user_id)
            )
            student = student_result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to fetch student for user_id {request.user_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error while retrieving student information"
            )

        if not student:
            logger.error("No student found for user_id: %s", request.user_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student not found for the provided user_id"
            )
        else:
            student_id = student.student_id
            filters = [
                JobPosting.is_active.is_(True),
                JobPosting.job_origin == request.job_origin,
                JobPosting.job_category_type == request.job_category_type,
            ]

            if request.work_type:
                try:
                    work_type = InternshipType[request.work_type]
                    filters.append(JobPosting.internship_type == work_type)
                except KeyError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid `type` value: {request.type}"
                    )
            if request.title:
                filters.append(JobPosting.title.ilike(f"%{request.title.strip()}%"))

            if request.job_type:
                try:
                    job_type = JobType[request.job_type]
                    filters.append(JobPosting.job_type == job_type)
                except KeyError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid `job_type` value: {request.job_type}"
                    )

            if request.location:
                filters.append(JobPosting.location.ilike(f"%{request.location.strip()}%"))

            if request.category:
                filters.append(JobPosting.category == request.category.strip())

            if request.role:
                filters.append(JobPosting.role == request.role.strip())

            # Pagination
            page = max(1, request.page)
            page_size = request.page_size
            offset = (page - 1) * page_size

            # Count total records
            total_stmt = select(func.count()).select_from(JobPosting).where(and_(*filters))
            total_result = await db.execute(total_stmt)
            total = total_result.scalar()

            # Query data
            stmt = (
                select(JobPosting)
                .order_by(desc(JobPosting.fetched_at))
                .where(and_(*filters))
                .offset(offset)
                .limit(page_size)
            )
            result = await db.execute(stmt)
            jobs = result.scalars().all()
            try:
                jobs = await refactor_response(data=jobs)
            except Exception as e:
                logger.error(f"Error refactoring job data: {e}")
                jobs = []
            if student_id:
                try:
                    bookmarks_result = await db.execute(
                        select(Bookmark).filter(Bookmark.student_id == student_id)
                    )
                    bookmarks = bookmarks_result.scalars().all()
                    bookmark_map = {bm.job_id: bm.bookmark_id for bm in bookmarks}
                except Exception as e:
                    logger.error(f"Error fetching bookmarks for student_id {student_id}: {e}")
                    bookmark_map = {}
                for job in jobs:
                    job.isSaved = job.job_id in bookmark_map
                    job.bookmark_id = bookmark_map.get(job.job_id)
            else:
                for job in jobs:
                    job.isSaved = False
                    job.bookmark_id = None

            return PaginatedInternshipResponse(
                items=jobs,
                total=total,
                page=page,
                page_size=page_size,
                total_pages=ceil(total / page_size),
                has_more=(offset + page_size) < total,
            )