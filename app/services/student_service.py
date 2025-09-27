from typing import Any, Dict, List
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database.models import Student
from app.database.models.users_models import User
from app.database.models.resume_extraction_models import (
    PersonalInfo, CompanyExperience, WorkExperience, 
    Skill, Certification, SocialProfile, 
    Education, Language, Projects
)
from app.schemas.student_schemas import (
    StudentUpdateSchema,
    SkillUpdateSchema, EducationUpdateSchema,
    ProjectUpdateSchema, CompanyExperienceUpdateSchema,
    WorkExperienceUpdateSchema
)


async def get_student(db: AsyncSession, student_id: UUID):
    result = await db.execute(select(Student).options(selectinload(Student.aspirations)).where(Student.student_id == student_id))
    student = result.scalars().first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


async def get_all_students(db: AsyncSession):
    result = await db.execute(select(Student).options(selectinload(Student.aspirations)))
    students = result.scalars().all()
    return students

class StudentService:
    @staticmethod
    async def update_student(db: AsyncSession, student_id: UUID, student_data: StudentUpdateSchema) -> Dict[str, Any]:
        """
        Update student details across multiple tables
        """
        # Get personal info for this student
        result = await db.execute(select(PersonalInfo).where(PersonalInfo.student_id == student_id))
        personal_info = result.scalars().first()
        
        if not personal_info:
            raise HTTPException(status_code=404, detail="Student not found")
        
        # Update personal info fields if provided
        if student_data.name is not None:
            personal_info.full_name = student_data.name
        if student_data.email is not None:
            personal_info.email = student_data.email
        if student_data.phone is not None:
            personal_info.phone = student_data.phone
        if student_data.location is not None:
            personal_info.location = student_data.location
        if student_data.bio is not None:
            personal_info.bio = student_data.bio

        # Update profile image path in users table if provided
        if student_data.profile_img_path is not None:
            # First, get the student record to find the user_id
            result = await db.execute(select(Student).where(Student.student_id == student_id))
            student = result.scalars().first()
            if not student:
                raise HTTPException(status_code=404, detail="Student not found")
            
            # Now get the user record using the user_id from student table
            result = await db.execute(select(User).where(User.user_id == student.user_id))
            user = result.scalars().first()
            if user:
                user.profile_img_path = student_data.profile_img_path
            else:
                raise HTTPException(status_code=404, detail="User record not found")
            
        # Update social profiles if provided
        # Update social profiles if any of the fields are provided
        if any(x is not None for x in [
            student_data.personal_website, student_data.linkedin, 
            student_data.github, student_data.twitter, student_data.website
        ]):
            # Find or create social profile
            result = await db.execute(select(SocialProfile).where(SocialProfile.user_id == personal_info.id))
            social_profile = result.scalars().first()
            
            if not social_profile:
                social_profile = SocialProfile(user_id=personal_info.id)
                db.add(social_profile)
            
            # Update only provided fields
            if student_data.personal_website is not None:
                social_profile.personal_website = student_data.personal_website
            if student_data.linkedin is not None:
                social_profile.linkedin = student_data.linkedin
            if student_data.github is not None:
                social_profile.github = student_data.github
            if student_data.twitter is not None:
                social_profile.twitter = student_data.twitter
            if student_data.website is not None:  # Support both naming formats
                social_profile.personal_website = student_data.website
        
        # Update skills if provided
        if student_data.skills is not None:
            StudentService._update_skills(db, personal_info.id, student_data.skills)
        
        # Update education records if provided
        if student_data.education is not None:
            StudentService._update_education(db, personal_info.id, student_data.education)
        
        # Update projects if provided
        if student_data.projects is not None:
            StudentService._update_projects(db, personal_info.id, student_data.projects)

        # Update certifications if provided in extra_fields
        if student_data.extra_fields and "certifications" in student_data.extra_fields:
            certifications_data = student_data.extra_fields["certifications"]
            StudentService._update_certifications_from_extra(db, personal_info.id, certifications_data)
            
        # Update languages if provided in extra_fields
        if student_data.extra_fields and "languages" in student_data.extra_fields:
            languages_data = student_data.extra_fields["languages"]
            StudentService._update_languages_from_extra(db, personal_info.id, languages_data)
                
        # Update company experiences if provided
        if student_data.experience is not None:
            StudentService._update_company_experiences(db, personal_info.id, student_data.experience)
        
        return {
            "status": "success",
            "message": "Student details updated successfully",
            "student_id": str(student_id)
        }

    @staticmethod
    async def _update_skills(db: AsyncSession, user_id: UUID, skills_data: SkillUpdateSchema):
        """
        Helper method to update skills grouped by categories.
        Only updates categories that are explicitly included in the skills_data.
        """
        # Get all existing skills for this user
        result = await db.execute(select(Skill).where(Skill.user_id == user_id))
        existing_skills = result.scalars().all()
        
        # Group existing skills by category for easier processing
        skills_by_category = {}
        for skill in existing_skills:
            if skill.category not in skills_by_category:
                skills_by_category[skill.category] = []
            skills_by_category[skill.category].append(skill)
        
        # Update programming languages if provided
        if skills_data.programming_languages is not None:
            # Remove existing skills in this category
            if "Programming Language" in skills_by_category:
                for skill in skills_by_category["Programming Language"]:
                    await db.delete(skill)
            
            # Add new skills
            for skill_name in skills_data.programming_languages:
                new_skill = Skill(
                    user_id=user_id,
                    skill_name=skill_name,
                    category="Programming Language"
                )
                db.add(new_skill)
        
        # Update tools and technologies if provided
        if skills_data.tools_technologies is not None:
            # Remove existing skills in this category
            if "Tool/Technology" in skills_by_category:
                for skill in skills_by_category["Tool/Technology"]:
                    await db.delete(skill)
            
            # Add new skills
            for skill_name in skills_data.tools_technologies:
                new_skill = Skill(
                    user_id=user_id,
                    skill_name=skill_name,
                    category="Tool/Technology"
                )
                db.add(new_skill)
        
        # Update soft skills if provided
        if skills_data.soft_skills is not None:
            # Remove existing skills in this category
            if "Soft Skill" in skills_by_category:
                for skill in skills_by_category["Soft Skill"]:
                    await db.delete(skill)
            
            # Add new skills
            for skill_name in skills_data.soft_skills:
                new_skill = Skill(
                    user_id=user_id,
                    skill_name=skill_name,
                    category="Soft Skill"
                )
                db.add(new_skill)
        
        # Update relevant courses if provided
        if skills_data.relevant_courses is not None:
            # Remove existing skills in this category
            if "Relevant Course" in skills_by_category:
                for skill in skills_by_category["Relevant Course"]:
                    await db.delete(skill)
            
            # Add new skills
            for skill_name in skills_data.relevant_courses:
                new_skill = Skill(
                    user_id=user_id,
                    skill_name=skill_name,
                    category="Relevant Course"
                )
                db.add(new_skill)

    @staticmethod
    async def _update_education(db: AsyncSession, user_id: UUID, education_data: List[EducationUpdateSchema]):
        """Helper method to update education records"""
        result = await db.execute(select(Education).where(Education.user_id == user_id))
        existing_education = {str(edu.id): edu for edu in result.scalars().all()}
    
        edu_ids_to_keep = set()
        
        for edu_data in education_data:
            if edu_data.id and str(edu_data.id) in existing_education:
                # Update existing education
                edu = existing_education[str(edu_data.id)]
                if edu_data.institution_name is not None:
                    edu.institution_name = edu_data.institution_name
                if edu_data.degree is not None:
                    edu.degree = edu_data.degree
                if edu_data.field_of_study is not None:
                    edu.field_of_study = edu_data.field_of_study
                if edu_data.start_date is not None:
                    edu.start_date = edu_data.start_date
                if edu_data.end_date is not None:
                    edu.end_date = edu_data.end_date
                if edu_data.grade is not None:
                    edu.grade = edu_data.grade
                if edu_data.description is not None:
                    edu.description = edu_data.description
                    
                edu_ids_to_keep.add(str(edu_data.id))
            else:
                # Add new education
                new_edu = Education(
                    user_id=user_id,
                    institution_name=edu_data.institution_name,
                    degree=edu_data.degree,
                    field_of_study=edu_data.field_of_study,
                    start_date=edu_data.start_date,
                    end_date=edu_data.end_date,
                    grade=edu_data.grade,
                    description=edu_data.description
                )
                db.add(new_edu)
        
        # Remove education records not included in the update
        for edu_id, edu in existing_education.items():
            if edu_id not in edu_ids_to_keep:
                await db.delete(edu)

    @staticmethod
    async def _update_projects(db: AsyncSession, user_id: UUID, projects_data: List[ProjectUpdateSchema]):
        """
        Helper method to update projects.
        Handles cases where project details might be a list of strings instead of a single string.
        """
        # Fetch all existing projects for this user asynchronously
        result = await db.execute(select(Projects).where(Projects.user_id == user_id))
        existing_projects = {str(proj.id): proj for proj in result.scalars().all()}
        
        project_ids_to_keep = set()
        
        for proj_data in projects_data:
            # Process details field - convert list to string if needed
            details_value = None
            if proj_data.details is not None:
                if isinstance(proj_data.details, list):
                    # Join list elements with a space or appropriate separator
                    details_value = "\n\n".join(proj_data.details)
                else:
                    details_value = proj_data.details
            
            if proj_data.id and str(proj_data.id) in existing_projects:
                # Update existing project
                proj = existing_projects[str(proj_data.id)]
                if proj_data.title is not None:
                    proj.title = proj_data.title
                if proj_data.dates is not None:
                    proj.dates = proj_data.dates
                if details_value is not None:
                    proj.details = details_value
                    
                project_ids_to_keep.add(str(proj_data.id))
            else:
                # Add new project
                new_proj = Projects(
                    user_id=user_id,
                    title=proj_data.title,
                    dates=proj_data.dates,
                    details=details_value
                )
                db.add(new_proj)
        
        # Remove projects not included in the update
        for proj_id, proj in existing_projects.items():
            if proj_id not in project_ids_to_keep:
                await db.delete(proj)
    @staticmethod
    async def _update_certifications_from_extra(db: AsyncSession, user_id: UUID, certifications_data: List[Dict[str, Any]]):
        """Async helper method to update certifications from extra_fields format"""
        result = await db.execute(select(Certification).where(Certification.user_id == user_id))
        existing_certifications = {str(cert.id): cert for cert in result.scalars().all()}
        
        cert_ids_to_keep = set()
        
        for cert_data in certifications_data:
            cert_id = cert_data.get("id")
            
            if cert_id and str(cert_id) in existing_certifications:
                # Update existing certification
                cert = existing_certifications[str(cert_id)]
                if "certification_name" in cert_data:
                    cert.certification_name = cert_data["certification_name"]
                if "issued_by" in cert_data:
                    cert.issued_by = cert_data["issued_by"]
                # Handle other fields...
                    
                cert_ids_to_keep.add(str(cert_id))
            else:
                # Add new certification
                new_cert = Certification(
                    user_id=user_id,
                    certification_name=cert_data.get("certification_name"),
                    issued_by=cert_data.get("issued_by")
                    # Set other fields...
                )
                db.add(new_cert)
        
        # Remove certifications not included in the update
        for cert_id, cert in existing_certifications.items():
            if cert_id not in cert_ids_to_keep:
                await db.delete(cert)

    @staticmethod
    async def _update_languages_from_extra(db: AsyncSession, user_id: UUID, languages_data: List[Dict[str, Any]]):
        """Helper method to update languages from extra_fields format"""
        result = await db.execute(select(Language).where(Language.user_id == user_id))
        existing_languages = {str(lang.id): lang for lang in result.scalars().all()}
            
        lang_ids_to_keep = set()
        
        for lang_data in languages_data:
            lang_id = lang_data.get("id")
            
            if lang_id and str(lang_id) in existing_languages:
                # Update existing language
                lang = existing_languages[str(lang_id)]
                if "language_name" in lang_data:
                    lang.language_name = lang_data["language_name"]
                if "proficiency_level" in lang_data:
                    lang.proficiency_level = lang_data["proficiency_level"]
                    
                lang_ids_to_keep.add(str(lang_id))
            else:
                # Add new language
                new_lang = Language(
                    user_id=user_id,
                    language_name=lang_data.get("language_name"),
                    proficiency_level=lang_data.get("proficiency_level")
                )
                db.add(new_lang)
        
        # Remove languages not included in the update
        for lang_id, lang in existing_languages.items():
            if lang_id not in lang_ids_to_keep:
                await db.delete(lang)

    @staticmethod
    async def _update_company_experiences(db: AsyncSession, user_id: UUID, 
                                    company_experiences_data: List[CompanyExperienceUpdateSchema]):
        """Helper method to update company experiences and their nested work experiences"""
        result = await db.execute(select(CompanyExperience).where(CompanyExperience.user_id == user_id))
        existing_companies = {str(comp.id): comp for comp in result.scalars().all()}
        company_ids_to_keep = set()
        
        for company_data in company_experiences_data:
            if company_data.id and str(company_data.id) in existing_companies:
                # Update existing company
                company = existing_companies[str(company_data.id)]
                
                if company_data.company_name is not None:
                    company.company_name = company_data.company_name
                if company_data.your_position is not None:
                    company.your_position = company_data.your_position
                if company_data.dates is not None:
                    company.dates = company_data.dates
                if company_data.company_website is not None:
                    company.company_website = company_data.company_website
                if company_data.company_location is not None:
                    company.company_location = company_data.company_location
                if company_data.company_description is not None:
                    company.company_description = company_data.company_description
                if company_data.company_logo is not None:
                    company.company_logo = company_data.company_logo
                
                company_ids_to_keep.add(str(company_data.id))
                
                # Handle nested work experiences
                if company_data.work_experiences is not None:
                    StudentService._update_work_experiences(db, company.id, company_data.work_experiences)
            else:
                # Add new company
                new_company = CompanyExperience(
                    user_id=user_id,
                    company_name=company_data.company_name,
                    your_position=company_data.your_position,
                    dates=company_data.dates,
                    company_website=company_data.company_website,
                    company_location=company_data.company_location,
                    company_description=company_data.company_description,
                    company_logo=company_data.company_logo
                )
                db.add(new_company)
                await db.flush()  # Get the ID for the new company
                
                # Add work experiences if provided
                if company_data.work_experiences:
                    StudentService._update_work_experiences(db, new_company.id, company_data.work_experiences)
        
        # Remove companies not included in the update
        for company_id, company in existing_companies.items():
            if company_id not in company_ids_to_keep:
                await db.delete(company)  # Will cascade delete work experiences
    
    @staticmethod
    async def _update_work_experiences(db: AsyncSession, company_id: UUID, work_experiences_data: List[WorkExperienceUpdateSchema]):
        """Helper method to update work experiences for a company"""
        result = await db.execute(select(WorkExperience).where(WorkExperience.company_id == company_id))
        existing_works = {str(work.id): work for work in result.scalars().all()}
        work_ids_to_keep = set()
        
        for work_data in work_experiences_data:
            if work_data.id and str(work_data.id) in existing_works:
                # Update existing work experience
                work = existing_works[str(work_data.id)]
                
                if work_data.position_title is not None:
                    work.position_title = work_data.position_title
                if work_data.company_name is not None:
                    work.company_name = work_data.company_name
                if work_data.duration is not None:
                    work.duration = work_data.duration
                if work_data.description is not None:
                    work.description = work_data.description
                
                work_ids_to_keep.add(str(work_data.id))
            else:
                # Add new work experience
                new_work = WorkExperience(
                    company_id=company_id,
                    position_title=work_data.position_title,
                    company_name=work_data.company_name,
                    duration=work_data.duration,
                    description=work_data.description
                )
                db.add(new_work)
        
        # Remove work experiences not included in the update
        for work_id, work in existing_works.items():
            if work_id not in work_ids_to_keep:
                 await db.delete(work)