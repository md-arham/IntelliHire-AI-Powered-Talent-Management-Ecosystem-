from collections import defaultdict
from uuid import UUID, uuid4
import os
import zipfile
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, UploadFile
from io import BytesIO
from app.database.models.employer_profiles_models import EmployerProfile
from app.database.models.job_postings_models import JobPosting
from app.utils.resume_extractor import extract_resume_data_v2
from app.utils.settings import embedding_model, settings, qdrant_client
from app.database.models.employer_resumes_models import (
    EmployerResume,
    EmployerResumeMatching,
    EmployerResumeSkill,
    EmployerResumeProject,
    EmployerResumeCertification,
    EmployerResumeEducation,
    EmployerResumePersonalInfo,
    EmployerResumeWorkExperience,
)
from sentence_transformers import util
from qdrant_client.http.models import Distance, PointStruct, VectorParams
from app.utils.logger_config import logger

async def store_personal_info(data: dict, resume_id: UUID, db: AsyncSession) -> UUID:
    personal_info = EmployerResumePersonalInfo(
        candidate_id=uuid4(),
        resume_id=resume_id,
        candidate_name=data.get("name"),
        email=data.get("email"),
        phone=data.get("phone"),
        location=data.get("location", ""),
        bio=data.get("objective", ""),
        language=", ".join(data.get("languages", [])) if data.get("languages") else "",
    )
    db.add(personal_info)
    await db.commit()
    await db.refresh(personal_info)
    return personal_info.candidate_id

async def store_skills(data: dict, candidate_id: UUID, db: AsyncSession):
    skills = data.get("skills", {})
    for category, skill_list in skills.items():
        for skill_name in skill_list:
            db.add(
                EmployerResumeSkill(
                    candidate_id=candidate_id, 
                    skill_name=skill_name, 
                    category=category
                )
            )
    await db.commit()

async def store_projects(data: dict, candidate_id: UUID, db: AsyncSession):
    for project in data.get("projects", []):
        db.add(
            EmployerResumeProject(
                candidate_id=candidate_id,
                title=project.get("title"),
                dates=project.get("dates", ""),
                details="\n".join(project.get("details", [])) if project.get("details") else "",
            )
        )
    await db.commit()

async def store_education(data: dict, candidate_id: UUID, db: AsyncSession):
    for edu in data.get("education", []):
        db.add(
            EmployerResumeEducation(
                candidate_id=candidate_id,
                institution_name=edu.get("institution", edu.get("institution_name", "")),
                degree=edu.get("degree"),
                field_of_study=", ".join(edu.get("details", [])) if edu.get("details") else "",
                start_date=None,
                end_date=None,
                grade="",
                description="",
            )
        )
    await db.commit()

async def store_work_experience(data: dict, candidate_id: UUID, db: AsyncSession):
    for exp in data.get("experience", []):
        db.add(
            EmployerResumeWorkExperience(
                candidate_id=candidate_id,
                company_name=exp.get("company", ""),
                position_title=exp.get("role", ""),
                duration=exp.get("dates", ""),
                description="\n".join(exp.get("details", [])) if exp.get("details") else "",
            )
        )
    await db.commit()

async def store_certifications(data: dict, candidate_id: UUID, db: AsyncSession):
    for cert in data.get("extra_fields", {}).get("certifications", []):
        db.add(
            EmployerResumeCertification(
                candidate_id=candidate_id,
                certification_name=cert.get("certification_name", ""),
                issued_by=cert.get("issued_by", ""),
                issue_date=None,
                expiration_date=None,
            )
        )
    await db.commit()


def save_resume_bytes_to_disk(
    file_bytes: bytes, original_filename: str, employer_id: UUID
) -> str:
    extension = os.path.basename(original_filename).split(".")[-1]
    filename = f"{uuid4()}.{extension}"

    employer_dir = os.path.join(
        settings.UPLOAD_EMPLOYER_RESUME_FOLDER, str(employer_id)
    )
    os.makedirs(employer_dir, exist_ok=True)

    file_path = os.path.join(employer_dir, filename)

    with open(file_path, "wb") as f:
        f.write(file_bytes)
    return file_path.replace("\\", "/")


async def process_resume_zip(db: AsyncSession, user_id: UUID, file: UploadFile):
    logger.info(f"Start processing resume ZIP for user_id: {user_id}")

    if not file.filename.lower().endswith(".zip"):
        logger.warning(f"File upload rejected: {file.filename} is not a ZIP.")
        raise HTTPException(status_code=400, detail="Only ZIP files are supported.")

    # Fetch employer profile
    employer_result = await db.execute(
        select(EmployerProfile).where(EmployerProfile.user_id == user_id)
    )
    employer = employer_result.scalars().first()
    if not employer:
        logger.error(f"Employer profile not found for user_id: {user_id}")
        raise HTTPException(status_code=404, detail="Employer profile not found.")
    employer_id = employer.employer_id
    logger.info(f"Employer ID fetched: {employer_id}")

    contents = await file.read()
    processed_files = []
    errors = []

    try:
        with zipfile.ZipFile(BytesIO(contents)) as z:
            resume_files = [
                f for f in z.namelist()
                if not f.endswith("/") and f.lower().endswith((".pdf", ".docx"))
            ]
            if not resume_files:
                logger.warning("No valid resume files found in the ZIP.")
                raise HTTPException(
                    status_code=400, detail="No valid resume files found in ZIP."
                )
            logger.info(f"Found {len(resume_files)} resume files in ZIP.")

            # Ensure Qdrant collection exists
            collections = await qdrant_client.get_collections()
            collection_names = [col.name for col in collections.collections]
            if settings.EMPLOYER_REFERAL_RESUME_COLLECTION_NAME not in collection_names:
                logger.info("Qdrant collection missing. Creating collection.")
                await qdrant_client.recreate_collection(
                    collection_name=settings.EMPLOYER_REFERAL_RESUME_COLLECTION_NAME,
                    vectors_config=VectorParams(size=384, distance=Distance.COSINE),
                )

            for filename in resume_files:
                logger.info(f"Processing file: {filename}")
                try:
                    with z.open(filename) as resume_file:
                        file_bytes = resume_file.read()
                        file_path = save_resume_bytes_to_disk(
                            file_bytes, filename, employer_id
                        )

                        try:
                            # Add resume to DB
                            resume = EmployerResume(
                                employer_id=employer_id,
                                filebytes=file_bytes,
                                file_path=file_path.replace("\\", "/"),
                                is_active=True,
                            )
                            db.add(resume)
                            await db.flush()
                            logger.info(f"Resume DB entry created for: {filename}")

                            # Extract and store resume data
                            resume_data = await extract_resume_data_v2(
                                BytesIO(file_bytes), filename
                            )
                            candidate_id = await store_personal_info(resume_data, resume.resume_id, db)
                            await store_skills(resume_data, candidate_id, db)
                            await store_projects(resume_data, candidate_id, db)
                            await store_education(resume_data, candidate_id, db)
                            await store_work_experience(resume_data, candidate_id, db)
                            await store_certifications(resume_data, candidate_id, db)
                            logger.info(f"Resume data extracted and stored for: {filename}")

                            # Vectorization for Qdrant
                            skills_dict = resume_data.get("skills", {})
                            skills_list = []
                            for skill_group in skills_dict.values():
                                skills_list.extend(skill_group)
                            skills_str = ", ".join(skills_list)
                            resume_vector = embedding_model.encode(
                                skills_str, normalize_embeddings=False
                            )

                            point = PointStruct(
                                id=str(resume.resume_id),
                                vector=resume_vector.tolist(),
                                payload={
                                    "skills": skills_list,
                                    "employer_id": str(employer_id),
                                    "filename": filename,
                                },
                            )
                            await qdrant_client.upsert(
                                collection_name=settings.EMPLOYER_REFERAL_RESUME_COLLECTION_NAME,
                                points=[point],
                            )
                            logger.info(f"Resume vectorized and upserted to Qdrant for: {filename}")

                            await db.commit()
                            processed_files.append(filename)
                            logger.info(f"Successfully processed: {filename}")

                        except Exception as e:
                            await db.rollback()
                            logger.error(f"Error processing {filename}: {e}")
                            errors.append(f"Error processing {filename}: {str(e)}")

                except Exception as e:
                    logger.error(f"Error reading {filename}: {e}")
                    errors.append(f"Error reading {filename}: {str(e)}")

            # Job matching
            try:
                stmt = select(JobPosting.job_id).where(
                    JobPosting.employer_id == employer_id,
                    JobPosting.job_origin == "INTERNAL",
                )
                job_ids_result = await db.execute(stmt)
                job_ids = job_ids_result.scalars().all()
                logger.info(f"Found {len(job_ids)} internal job postings for employer.")

                for job_id in job_ids:
                    try:
                        result = await match_resumes_to_job(db, job_id)
                        if result["errors"]:
                            logger.warning(f"Errors in job matching for job_id {job_id}: {result['errors']}")
                            errors.extend(result["errors"])
                    except Exception as e:
                        logger.error(f"Error matching resumes for job_id {job_id}: {e}")
                        errors.append(
                            f"Error matching resumes for job_id {job_id}: {str(e)}"
                        )
            except Exception as e:
                logger.error(f"Error fetching job_ids for employer: {e}")
                errors.append(f"Error fetching job_ids for employer: {str(e)}")

    except zipfile.BadZipFile:
        logger.error("Uploaded file is not a valid ZIP archive.")
        raise HTTPException(
            status_code=400, detail="Uploaded file is not a valid ZIP archive."
        )
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

    logger.info(f"Processing complete. {len(processed_files)} files processed, {len(errors)} errors.")
    return {
        "processed_files": processed_files,
        "errors": errors,
        "message": f"Processed {len(processed_files)} files. {len(errors)} errors.",
    }


async def match_resumes_to_job(db: AsyncSession, job_id: UUID):
    processed_resumes = []
    errors = []

    # 1. Retrieve job vector from Qdrant (async)
    try:
        job_result = await qdrant_client.retrieve(
            collection_name=settings.JOB_COLLECTION_NAME,
            ids=[str(job_id)],
            with_vectors=True,
        )
        if not job_result:
            raise ValueError(f"No vector found for job_id={job_id}")
        job_vector = job_result[0].vector
    except Exception as e:
        return {
            "processed_resumes": [],
            "errors": [f"Job vector retrieval failed: {str(e)}"],
            "message": "Failed to process any resumes.",
        }

    # 2. Get all resume_ids from employer_resumes (async)
    resume_ids_result = await db.execute(
        select(EmployerResume.resume_id)
    )
    resume_ids = resume_ids_result.scalars().all()

    # 3. Async processing for each resume
    for resume_id in resume_ids:
        try:
            # Async Qdrant retrieval
            resume_result = await qdrant_client.retrieve(
                collection_name=settings.EMPLOYER_REFERAL_RESUME_COLLECTION_NAME,
                ids=[str(resume_id)],
                with_vectors=True,
            )
            if not resume_result:
                errors.append(f"No vector found for resume_id={resume_id}")
                continue

            resume_vector = resume_result[0].vector
            similarity = util.cos_sim(job_vector, resume_vector).item()
            matching_score = round(similarity * 100, 2)

            # Async database check
            existing_result = await db.execute(
                select(EmployerResumeMatching)
                .where(
                    (EmployerResumeMatching.job_id == job_id) &
                    (EmployerResumeMatching.resume_id == resume_id)
                )
            )
            existing = existing_result.scalars().first()

            if not existing:
                matching = EmployerResumeMatching(
                    job_id=job_id,
                    resume_id=resume_id,
                    matching_score=matching_score,
                    matching_reason=None,
                    selection_status=False,
                )
                db.add(matching)
                processed_resumes.append(str(resume_id))
                
        except Exception as e:
            errors.append(f"Error processing resume_id={resume_id}: {str(e)}")

    await db.commit()  # Async commit

    return {
        "processed_resumes": processed_resumes,
        "errors": errors,
        "message": f"Matched {len(processed_resumes)} resumes. {len(errors)} errors.",
    }


async def get_jobs_and_resumes_by_employer(db: AsyncSession, user_id: UUID):
    # Get employer profile (async)
    employer_result = await db.execute(
        select(EmployerProfile).where(EmployerProfile.user_id == user_id)
    )
    employer = employer_result.scalars().first()
    if not employer:
        return []
    employer_id = employer.employer_id

    # Get job IDs (async)
    job_stmt = select(JobPosting.job_id).where(
        JobPosting.employer_id == employer_id, 
        JobPosting.job_origin == "INTERNAL"
    )
    job_ids_result = await db.execute(job_stmt)
    job_ids = job_ids_result.scalars().all()

    result = []

    for job_id in job_ids:
        # Execute main query (async)
        matching_stmt = (
            select(
                EmployerResumeMatching.resume_id,
                EmployerResumeMatching.matching_score,
                EmployerResumeMatching.matching_reason,
                EmployerResumeMatching.selection_status,
                EmployerResumePersonalInfo.candidate_id,
                EmployerResumePersonalInfo.candidate_name,
                EmployerResumePersonalInfo.email,
                EmployerResumePersonalInfo.phone,
                EmployerResumePersonalInfo.location,
                EmployerResumePersonalInfo.bio,
                EmployerResumePersonalInfo.language,
            )
            .join(
                EmployerResumePersonalInfo,
                EmployerResumeMatching.resume_id == EmployerResumePersonalInfo.resume_id,
            )
            .where(EmployerResumeMatching.job_id == job_id)
            .order_by(desc(EmployerResumeMatching.matching_score))
        )

        resumes_result = await db.execute(matching_stmt)
        resumes_rows = resumes_result.all()

        resumes = []

        for row in resumes_rows:
            candidate_id = row.candidate_id

            # Async skills query
            skills_stmt = select(
                EmployerResumeSkill.category, 
                EmployerResumeSkill.skill_name
            ).where(EmployerResumeSkill.candidate_id == candidate_id)
            
            skills_result = await db.execute(skills_stmt)
            skills_rows = skills_result.all()
            skills = defaultdict(list)
            for skill_row in skills_rows:
                cat = skill_row.category or "Uncategorized"
                skills[cat].append(skill_row.skill_name)

            # Async projects query
            projects_stmt = select(
                EmployerResumeProject.title,
                EmployerResumeProject.dates,
                EmployerResumeProject.details,
            ).where(EmployerResumeProject.candidate_id == candidate_id)
            
            projects_result = await db.execute(projects_stmt)
            projects_rows = projects_result.all()
            projects = []
            for proj_row in projects_rows:
                projects.append({
                    "title": proj_row.title,
                    "dates": proj_row.dates,
                    "details": proj_row.details,
                })

            # Async work experience query
            work_stmt = select(
                EmployerResumeWorkExperience.company_name,
                EmployerResumeWorkExperience.position_title,
                EmployerResumeWorkExperience.duration,
                EmployerResumeWorkExperience.description,
            ).where(EmployerResumeWorkExperience.candidate_id == candidate_id)
            
            work_result = await db.execute(work_stmt)
            work_rows = work_result.all()
            work_experiences = []
            for work_row in work_rows:
                work_experiences.append({
                    "company_name": work_row.company_name,
                    "position_title": work_row.position_title,
                    "duration": work_row.duration,
                    "description": work_row.description,
                })

            # Async education query
            education_stmt = select(
                EmployerResumeEducation.institution_name,
                EmployerResumeEducation.degree,
                EmployerResumeEducation.field_of_study,
                EmployerResumeEducation.start_date,
                EmployerResumeEducation.end_date,
                EmployerResumeEducation.grade,
                EmployerResumeEducation.description,
            ).where(EmployerResumeEducation.candidate_id == candidate_id)
            
            education_result = await db.execute(education_stmt)
            education_rows = education_result.all()
            education = []
            for edu_row in education_rows:
                education.append({
                    "institution_name": edu_row.institution_name,
                    "degree": edu_row.degree,
                    "field_of_study": edu_row.field_of_study,
                    "start_date": str(edu_row.start_date) if edu_row.start_date else None,
                    "end_date": str(edu_row.end_date) if edu_row.end_date else None,
                    "grade": edu_row.grade,
                    "description": edu_row.description,
                })

            # Async certifications query
            cert_stmt = select(
                EmployerResumeCertification.certification_name,
                EmployerResumeCertification.issued_by,
                EmployerResumeCertification.issue_date,
                EmployerResumeCertification.expiration_date,
            ).where(EmployerResumeCertification.candidate_id == candidate_id)
            
            cert_result = await db.execute(cert_stmt)
            cert_rows = cert_result.all()
            certifications = []
            for cert_row in cert_rows:
                certifications.append({
                    "certification_name": cert_row.certification_name,
                    "issued_by": cert_row.issued_by,
                    "issue_date": str(cert_row.issue_date) if cert_row.issue_date else None,
                    "expiration_date": str(cert_row.expiration_date) if cert_row.expiration_date else None,
                })

            # Build resume dict
            resume_dict = {
                "resume_id": str(row.resume_id),
                "matching_score": row.matching_score,
                "matching_reason": row.matching_reason,
                "selection_status": row.selection_status,
                "candidate_name": row.candidate_name,
                "email": row.email,
                "phone": row.phone,
                "location": row.location,
                "bio": row.bio,
                "language": row.language,
                "skills": dict(skills),
                "projects": projects,
                "work_experiences": work_experiences,
                "education": education,
                "certifications": certifications,
            }
            resumes.append(resume_dict)

        result.append({str(job_id): resumes})

    return result