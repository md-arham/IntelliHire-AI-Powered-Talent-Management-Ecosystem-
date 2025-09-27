from typing import List, Tuple

def get_strengths_and_gaps(resume_skills_str: str, job_skills_str: str) -> Tuple[List[str], List[str]]:
    """
    Compares resume skills with job-required skills and returns strengths and gaps.

    Args:
        resume_skills_str (str): Comma-separated resume skills (e.g., "Python, SQL, FastAPI").
        job_skills_str (str): Comma-separated job skills (e.g., "Python, Docker, REST").

    Returns:
        Tuple[List[str], List[str]]: (strengths, gaps)
            - strengths: Job skills that match resume skills.
            - gaps: Job skills not found in resume skills.
    """
    # Step 1: Tokenize resume skills into a flat set of words
    resume_skills = [skill.strip().lower() for skill in resume_skills_str.split(",") if skill.strip()]
    resume_skills_set = set(resume_skills)

    # Step 2: Process job skills
    job_skills = [skill.strip().lower() for skill in job_skills_str.split(",") if skill.strip()]
    

    strengths = []
    gaps = []

    # Step 3: For each job skill, check if any word overlaps
    for job_skill in set(job_skills):
            if job_skill in resume_skills_set:
                strengths.append(job_skill)
            else:
                gaps.append(job_skill)

    return strengths, gaps
