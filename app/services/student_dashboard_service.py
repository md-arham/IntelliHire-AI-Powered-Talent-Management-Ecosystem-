from uuid import UUID
from typing import List, Union
from fastapi import HTTPException
from app.database.models.companies_models import Company
from app.database.models import Student,JobCandidateMatching,JobCandidateScreening,EmployerProfile
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from app.database.models import(
    JobApplicationStatus,
    JobApplication,
    ResumeScreeningInternship,
    ResumeScreeningResult,
    JobPosting
)
from app.utils.logger_config import logger
from sqlalchemy.exc import SQLAlchemyError

async def get_dashboard_stats_for_user(user_id: UUID, db: AsyncSession):
    try:
        # Step 1: Fetch student_id from user_id (async)
        student_result = await db.execute(
            select(Student).where(Student.user_id == user_id)
        )
        student = student_result.scalars().first()
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        student_id = student.student_id
        try:
            # Step 2: Get total internship and job posting count (async)
            total_job_postings_result = await db.execute(
                select(func.count(JobPosting.job_id)).where(JobPosting.is_active)
            )
            total_job_postings = total_job_postings_result.scalar_one()
        except SQLAlchemyError as e:
            logger.error(f"Failed to fetch total job postings: {e}")
            raise HTTPException(status_code=500, detail="Failed to retrieve job postings")

        try:
            # Step 3: Get recommended internships count for this student (async)
            recommended_internships_result = await db.execute(
                select(func.count(ResumeScreeningInternship.internship_id))
                .select_from(ResumeScreeningInternship)
                .join(
                    ResumeScreeningResult,
                    ResumeScreeningResult.screening_id == ResumeScreeningInternship.screening_id,
                )
                .where(ResumeScreeningResult.student_id == student_id)
            )
            recommended_internships = recommended_internships_result.scalar_one()
        except SQLAlchemyError as e:
            logger.error(f"Failed to fetch recommended internships: {e}")
            raise HTTPException(status_code=500, detail="Failed to retrieve recommended internships")

        try:
            # Step 4: Job applications count grouped by status (async)
            db_status_counts_result = await db.execute(
                select(JobApplication.status, func.count(JobApplication.application_id))
                .where(JobApplication.student_id == student_id)
                .group_by(JobApplication.status)
            )
            db_status_counts = db_status_counts_result.all()
        except SQLAlchemyError as e:
            logger.error(f"Failed to fetch job application status counts: {e}")
            raise HTTPException(status_code=500, detail="Failed to retrieve job application status counts")

        # Initialize with all status values set to 0
        status_summary = {status.value: 0 for status in JobApplicationStatus}

        # Update counts from database results
        for status, count in db_status_counts:
            status_summary[status.value] = count

        return {
            "total_postings": total_job_postings,
            "recommended_internships": recommended_internships,
            "job_application_status_counts": status_summary,
        }
    except Exception as e:
        logger.error(f"Unexpected error while generating dashboard stats for user_id {user_id}: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred")
    

async def get_employer_profiles_for_user(user_id: UUID, db: AsyncSession, company_type: str = None) -> Union[List[dict], dict]:
    # Step 1: Get student_id from user_id
    student_result = await db.execute(
        select(Student).where(Student.user_id == user_id)
    )
    student = student_result.scalars().first()
    if not student:
        return {"message": "Student profile not found. Please complete your profile to get noticed by employers!"}

    student_id = student.student_id

    # Step 2: Get screening_ids from job_candidate_matching table
    screening_ids_result = await db.execute(
        select(JobCandidateMatching.screening_id)
        .where(JobCandidateMatching.student_id == student_id)
        .distinct()
    )
    screening_ids = [s[0] for s in screening_ids_result.all()]
    if not screening_ids:
        return {"message": "Keep building your skills and updating your resume! Opportunities are just around the corner."}

    # Step 3: Get unique employer_ids from job_candidate_screening table
    employer_ids_result = await db.execute(
        select(JobCandidateScreening.employer_id)
        .where(JobCandidateScreening.screening_id.in_(screening_ids))
        .distinct()
    )
    employer_ids = [e[0] for e in employer_ids_result.all()]
    if not employer_ids:
        return {"message": "You're making progress! Continue applying and refining your profile to attract more employers."}

    # Step 4: Query EmployerProfile joined with Company
    query = (
        select(EmployerProfile)
        .join(EmployerProfile.company)
        .options(joinedload(EmployerProfile.company))
        .where(EmployerProfile.employer_id.in_(employer_ids))
    )
    
    if company_type:
        query = query.where(Company.type == company_type)

    employer_profiles_result = await db.execute(query)
    employer_profiles = employer_profiles_result.scalars().all()

    # Step 5: Build response (unchanged)
    employer_list = []
    for emp in employer_profiles:
        company = emp.company
        emp_dict = {
            "employer_id": str(emp.employer_id),
            "company_name": company.name if company else None,
            "company_type": company.type.name if company and company.type else None,
            "description": company.description if company else None,
            "logo_url": company.logo_url if company else None,
            "website_url": company.website_url if company else None,
            "created_at": emp.created_at
        }
        employer_list.append(emp_dict)

    return employer_list
