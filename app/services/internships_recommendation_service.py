from math import ceil
from app.database.models.bookmark_models import Bookmark
from app.database.models.enums_models import InternshipType, JobType
from app.database.models.job_applications_models import JobApplication
from app.schemas.internships_schema import InternshipFilterRequest
from app.schemas.job_postings_schema import PaginatedInternshipResponse
from app.services.internships_service import refactor_response
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional, Any, Dict, List
from uuid import UUID
from app.utils.settings import (
    embedding_model,
    settings,
    qdrant_client,
)
import asyncio
from app.utils.logger_config import logger
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from app.database.models.job_postings_models import JobOriginType, JobPosting
from app.database.models.resume_screening_internship_models import (
    ResumeScreeningInternship,
)
from app.database.models.resume_screening_results_models import ResumeScreeningResult
from app.database.models.resume_versions_models import ResumeVersion
from app.database.models.students_models import Student
from app.utils.summarize_descriptions import summarize_jobs_with_llm

# Initialize clients/models
COLLECTION_NAME = settings.INTERNSHIPS_COLLECTION_NAME
BATCH_SIZE = settings.BATCH_SIZE

async def upload_internships_to_qdrant_v2(db: AsyncSession) -> dict:
    """
    Uploads the most recently fetched external internships into the Qdrant vector database.

    Steps:
    - Fetch internships added in the last 5 minutes, fallback to the latest 50 if none.
    - Process internships into vectors and payloads.
    - Ensure Qdrant collection exists.
    - Upsert internship data into Qdrant.

    Args:
        db (AsyncSession): Asynchronous SQLAlchemy database session.

    Returns:
        dict: Response indicating upload status and number of processed internships.
    """
    try:
        current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        start_time = current_time - timedelta(minutes=5)

        logger.info(f" Fetching internships from {start_time} to {current_time}")

        try:
            result = await db.execute(
                JobPosting.__table__.select().where(
                    JobPosting.is_active.is_(True),
                    JobPosting.job_origin == JobOriginType.EXTERNAL,
                    JobPosting.fetched_at.between(start_time, current_time),
                ).limit(50)
            )
            internships = result.fetchall()

            if not internships:
                logger.info("Primary query returned no results, trying fallback query.")
                result = await db.execute(
                    JobPosting.__table__.select().where(
                        JobPosting.is_active.is_(True),
                        JobPosting.job_origin == JobOriginType.EXTERNAL,
                    ).order_by(JobPosting.fetched_at.desc()).limit(50)
                )
                internships = result.fetchall()

            if not internships:
                logger.warning(" No internships found to upload.")
                return {"status": "no_data", "processed": 0}

        except Exception as db_error:
            logger.error(" Database query failed.", exc_info=db_error)
            return {"status": "error", "message": f"DB error: {str(db_error)}"}

        logger.info(f" Processing {len(internships)} internships...")
        all_processed_data = await process_internship_batch(internships)

        if not all_processed_data:
            logger.warning(" No valid internship data was processed.")
            return {"status": "no_data", "processed": 0}
        
        logger.info(all_processed_data[0])

        await ensure_qdrant_collection()
        try:
            points = [
                PointStruct(
                    id=item["id"],
                    vector=item["vector"],
                    payload=item["payload"]
                ) for item in all_processed_data
            ]

            await qdrant_client.upsert(
                collection_name=COLLECTION_NAME,
                points=points
            )

            logger.info(f" Successfully upserted {len(points)} internships into Qdrant.")
            return {"status": "success", "processed": len(points)}

        except Exception as upsert_error:
            logger.error(" Failed to upsert points into Qdrant.", exc_info=upsert_error)
            return {"status": "error", "message": f"Qdrant upsert error: {str(upsert_error)}"}

    except Exception as e:
        logger.error(f" Unexpected error in upload_internships_to_qdrant_v2: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}



async def process_internship_batch(internships: list) -> List[Dict[str, Any]]:
    processed = []
    total_batches = (len(internships) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_index in range(total_batches):
        start = batch_index * BATCH_SIZE
        end = start + BATCH_SIZE
        batch = internships[start:end]

        logger.info(f"\n Processing Batch {batch_index + 1} of {total_batches} ({len(batch)} internships)")

        batch_tasks = [process_internship(job) for job in batch]
        results = await asyncio.gather(*batch_tasks, return_exceptions=True)

        success_count = 0

        for idx, result in enumerate(results):
            if isinstance(result, dict):
                processed.append(result)
                success_count += 1
            elif isinstance(result, Exception):
                logger.error(f" Internship {start + idx + 1} in Batch {batch_index + 1} failed", exc_info=result)
            elif result is None:
                logger.warning(f" Internship {start + idx + 1} in Batch {batch_index + 1} returned None.")

        logger.info(f" Batch {batch_index + 1} completed — Success: {success_count}/{len(batch)}")

    logger.info(f"\n All batches processed — Total Success: {len(processed)}/{len(internships)}\n")
    return processed

async def process_internship(internship) -> Optional[dict[str, any]]:
    """
    Process a single internship with detailed logging
    """
    internship_id = internship.job_id
    logger.debug(f"Starting to process internship {internship_id}")

    try:
        title = internship.title
        description = internship.description or ""
        skills_required = internship.required_skills or ""
        requirements = internship.requirements or ""
        responsibilities = internship.responsibilities or ""

        job_text = f"Title: {title}\nDescription: {description}\nSkills required: {skills_required}\nRequirements: {requirements}\nResponsibilities: {responsibilities}"

        logger.debug(f"Job text length for {internship_id}: {len(job_text)} characters")
        logger.info(f"Sending request to LLM for internship {internship_id}")

        internship_data = await summarize_jobs_with_llm(job_text)

        # Generate embedding
        logger.info(f"Generating embedding for internship {internship_id}")
        skills_text = internship_data.get("skills") or title

        embedding = embedding_model.encode(skills_text, normalize_embeddings=False)

        logger.info(
            f"Generated embedding of size {len(embedding)} for internship {internship_id}"
        )

        result = {
            "id": str(internship_id),
            "vector": embedding.tolist(),
            "payload": {
                "title": title,
                "summary": internship_data
            },
        }

        logger.info(f"Successfully processed internship {internship_id}")
        return result

    except asyncio.TimeoutError:
        logger.error(f"Timeout processing internship {internship_id}")
        return None
    except Exception as e:
        logger.error(
            f"Error processing internship {internship_id}: {str(e)}", exc_info=True
        )
        return None


async def ensure_qdrant_collection():
    """
    Ensure Qdrant collection exists with proper error handling
    """
    try:
        logger.info("Checking existing Qdrant collections...")
        existing_collections = await qdrant_client.get_collections()
        collection_names = [col.name for col in existing_collections.collections]

        logger.info(f"Existing collections: {collection_names}")

        if COLLECTION_NAME not in collection_names:
            logger.info(f"Creating collection '{COLLECTION_NAME}'...")
            await qdrant_client.recreate_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )
            logger.info(f"Successfully created collection '{COLLECTION_NAME}'")
        else:
            logger.info(f"Collection '{COLLECTION_NAME}' already exists")

    except Exception as e:
        logger.error(f"Error ensuring Qdrant collection: {e}", exc_info=True)
        raise



async def get_recommendations_by_resume_version(
    user_id: UUID, db: AsyncSession
) -> dict:
    """
    Generate internal and external job recommendations for each resume version of a student.

    Args:
        user_id (UUID): UUID of the user (student).
        db (AsyncSession): Asynchronous database session.

    Returns:
        dict: Resume name mapped to a list of job recommendations (internal + external combined).
    """
    try:
        student_result = await db.execute(
            select(Student).where(Student.user_id == user_id)
        )
        student = student_result.scalar_one_or_none()
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        # Resume name mapping
        version_result = await db.execute(
            select(ResumeVersion.version_id, ResumeVersion.resume_name).where(
                ResumeVersion.student_id == student.student_id
            )
        )
        version_map = {
            str(row.version_id): row.resume_name for row in version_result.all()
        }

        screenings_result = await db.execute(
            select(ResumeScreeningResult).where(
                ResumeScreeningResult.student_id == student.student_id
            )
        )
        screenings = screenings_result.scalars().all()
        if not screenings:
            return {}

        # Group screening_ids by resume version
        screenings_by_version = defaultdict(list)
        for s in screenings:
            screenings_by_version[str(s.version_id)].append(s.screening_id)

        final_result = {}

        for version_id, screening_ids in screenings_by_version.items():
            resume_name = version_map.get(version_id)
            if not resume_name:
                continue

            combined_recommendations = []

            for source in ["Internal", "External"]:
                internship_result = await db.execute(
                    select(ResumeScreeningInternship)
                    .where(
                        ResumeScreeningInternship.screening_id.in_(screening_ids),
                        ResumeScreeningInternship.source == source,
                    )
                    .order_by(ResumeScreeningInternship.matching_score.desc().nullslast())
                )
                internship_links = internship_result.scalars().all()

                if not internship_links:
                    continue

                internship_info = [
                (link.internship_id, link.matching_score, link.matching_skills, link.missing_skills)
                    for link in internship_links
                ]
                ids = [i[0] for i in internship_info]

                job_result = await db.execute(
                    select(JobPosting).where(JobPosting.job_id.in_(ids))
                )
                job_postings = job_result.scalars().all()
                job_map = {str(j.job_id): j for j in job_postings}

                for internship_id, score, matching_skills,missing_skills in internship_info:
                    job = job_map.get(str(internship_id))
                    if job:
                        job_data = jsonable_encoder(job)
                        job_data["id"] = str(job.job_id)
                        job_data["matching_score"] = score
                        job_data["matching_skills"] = matching_skills
                        job_data["missing_skills"] = missing_skills
                        job_data["source"] = (
                            "LinkedIn" if source == "External" else "Internal"
                        )
                        combined_recommendations.append(job_data)

            if combined_recommendations:
                final_result[resume_name] = sorted(
                    combined_recommendations,
                    key=lambda x: x["matching_score"],
                    reverse=True,
                )

        return final_result

    except Exception as e:
        logger.exception(f"Error in by-version recommendation service: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def get_filtered_paginated_recommended_internships(
    request: InternshipFilterRequest,
    db: AsyncSession
) -> PaginatedInternshipResponse:
    try:
        # Step 1: Get student
        student_result = await db.execute(
            select(Student).where(Student.user_id == request.user_id)
        )
        student = student_result.scalar_one_or_none()
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        # Step 2: Get resume screening ids
        screening_result = await db.execute(
            select(ResumeScreeningResult.screening_id).where(
                ResumeScreeningResult.student_id == student.student_id
            )
        )
        screening_ids = [r[0] for r in screening_result.all()]
        if not screening_ids:
            return PaginatedInternshipResponse(
                items=[], total=0, page=request.page,
                page_size=request.page_size, total_pages=0, has_more=False
            )

        # Step 3: Get internship links
        filters = [ResumeScreeningInternship.screening_id.in_(screening_ids)]
        if request.job_origin == JobOriginType.INTERNAL:
            filters.append(ResumeScreeningInternship.source == "Internal")
        elif request.job_origin == JobOriginType.EXTERNAL:
            filters.append(ResumeScreeningInternship.source == "External")

        internship_links_result = await db.execute(
            select(ResumeScreeningInternship).where(*filters)
        )
        links = internship_links_result.scalars().all()
        if not links:
            return PaginatedInternshipResponse(
                items=[], total=0, page=request.page,
                page_size=request.page_size, total_pages=0, has_more=False
            )

        # link_info only includes score & reason
        link_info = {
            str(link.internship_id): {
                "matching_score": link.matching_score,
                "matching_skills": link.matching_skills,
                "missing_skills": link.missing_skills
            } for link in links
        }
        job_ids = list(link_info.keys())

        # Step 4: Build job query with filters
        job_query = select(JobPosting).where(
            JobPosting.job_id.in_(job_ids),
            JobPosting.is_active.is_(True)
        )

        # Exclude internal internships that the student has already applied to
        # to avoid recommending jobs they've already interacted with.
        if request.job_origin == JobOriginType.INTERNAL:
            applied_subquery = (
                select(JobApplication.job_id)
                .filter(JobApplication.student_id == student.student_id)
                .subquery()
            )
            job_query = job_query.where(~JobPosting.job_id.in_(applied_subquery))


        if request.job_category_type:
            job_query = job_query.where(JobPosting.job_category_type == request.job_category_type)
        if request.work_type:
            try:
                work_type = InternshipType[request.work_type]
                job_query = job_query.where(JobPosting.internship_type == work_type)
            except KeyError:
                raise HTTPException(status_code=400, detail=f"Invalid work_type: {request.work_type}")
        if request.job_type:
            try:
                job_type = JobType[request.job_type]
                job_query = job_query.where(JobPosting.job_type == job_type)
            except KeyError:
                raise HTTPException(status_code=400, detail=f"Invalid job_type: {request.job_type}")
        if request.location:
            job_query = job_query.where(JobPosting.location.ilike(f"%{request.location}%"))
        if request.category:
            job_query = job_query.where(JobPosting.category.ilike(f"%{request.category}%"))
        if request.role:
            job_query = job_query.where(JobPosting.role.ilike(f"%{request.role}%"))
        if request.title:
            job_query = job_query.where(JobPosting.title.ilike(f"%{request.title}%"))

        all_results = await db.execute(job_query)
        jobs = all_results.scalars().all()

        # Step 5: Apply refactor_response if external
        if request.job_origin == JobOriginType.EXTERNAL:
            try:
                jobs = await refactor_response(data=jobs)
            except Exception as e:
                logger.error(f"Error in refactor_response: {e}")
                jobs = []

        # Step 6: Fetch bookmarks
        bookmark_map = {}
        try:
            bookmark_result = await db.execute(
                select(Bookmark).filter(Bookmark.student_id == student.student_id)
            )
            bookmarks = bookmark_result.scalars().all()
            bookmark_map = {bm.job_id: bm.bookmark_id for bm in bookmarks}
        except Exception as e:
            logger.error(f"Error fetching bookmarks: {e}")

        # Step 7: Enrich job postings
        enriched_jobs = []
        for job in jobs:
            jid = str(job.job_id)
            if jid in link_info:
                job.isSaved = job.job_id in bookmark_map
                job.bookmark_id = bookmark_map.get(job.job_id)

                # Add matching score and reason to additional_info
                if not job.additional_info or not isinstance(job.additional_info, dict):
                    job.additional_info = {}

                job.additional_info.update({
                    "matching_score": link_info[jid]["matching_score"],
                    "matching_skills": link_info[jid]["matching_skills"],
                    "missing_skills" : link_info[jid]["missing_skills"],
                    "job_origin": job.job_origin.value,
                    "job_category_type": job.job_category_type.value,
                })

                enriched_jobs.append(job)

        # Step 8: Sort by matching_score
        enriched_jobs.sort(key=lambda x: x.additional_info.get("matching_score") or 0, reverse=True)

        # Step 9: Pagination
        total = len(enriched_jobs)
        page = max(1, request.page)
        page_size = request.page_size
        offset = (page - 1) * page_size
        paginated_jobs = enriched_jobs[offset: offset + page_size]

        return PaginatedInternshipResponse(
            items=paginated_jobs,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=ceil(total / page_size),
            has_more=(offset + page_size) < total
        )

    except Exception as e:
        logger.error(f"Error in recommended internship fetch: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
