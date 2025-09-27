import logging
from uuid import UUID, uuid4
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams
from sentence_transformers import util
from sqlalchemy.orm import Session
from qdrant_client.http import models
from app.database.models import (
    Education,
    PersonalInfo,
    ResumeScreeningInternship,
    ResumeScreeningResult,
    ResumeVersion,
    Skill,
    JobPosting,
    JobCandidateScreening,
    JobCandidateMatching,
)
from app.utils.settings import chat, embedding_model, settings
import json
import re

# Configuration
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = settings.RESUMES_COLLECTION_NAME
INTERNSHIP_COLLECTION = settings.INTERNSHIPS_COLLECTION_NAME
VECTOR_SIZE = 384  # for all-MiniLM-L6-v2
SIMILARITY_THRESHOLD = 0.65

# Logger setup
logger = logging.getLogger("resume_logger")
logger.setLevel(logging.INFO)

# Model and client

qdrant_client = QdrantClient(url=QDRANT_URL)

TIER_DATA = {
    "tier1": [
        "acharya nagarjuna university",
        "alagappa university",
        "aligarh muslim university amu",
        "all india institute of medical sciences (aiims) bhopal",
        "all india institute of medical sciences (aiims) bhubaneswar",
        "all india institute of medical sciences (aiims) jodhpur",
        "all india institute of medical sciences (aiims) new delhi",
        "all india institute of medical sciences (aiims) patna",
        "all india institute of medical sciences (aiims) raipur",
        "all india institute of medical sciences (aiims) rishikesh",
        "amrita vishwa vidyapeetham, coimbatore",
        "andhra university waltair visakhapatnam",
        "annamalai university",
        "anna university, chennai",
        "anna university, coimbatore",
        "anna university, tiruchirappalli",
        "anna university, tirunelveli",
        "babasaheb bhimrao ambedkar university, lucknow",
        "banaras hindu university (bhu)",
        "banasthali vidyapith",
        "bangalore university (bu)",
        "berhampur university",
        "bharathiar university",
        "bharathidasan university",
        "bharath institute of higher education and research (biher), chennai",
        "bharath institute of higher education and research (biher)",
        "bharati vidyapeeth",
        "birla institute of technology & science (bits pilani)",
        "b.s. abdur rahman crescent institute of science and technology, chennai",
        "b.s. abdur rahman crescent institute of science and technology",
        "central institute of fisheries education (cife), mumbai",
        "central institute of higher tibetan studies (cihts)",
        "central institute of technology, kokrajhar (citk)",
        "centurion university of technology and management, paralakhemundi",
        "charotar university of science and technology (charusat)",
        "chennai mathematical institute (cmi)",
        "icfai foundation for higher education, hyderabad",
        "indian agricultural research institute ((iari), new delhi",
        "indian institute of foreign trade (iift), new delhi",
        "indian institute of information technology, allahabad (iiit-allahabad)",
        "indian institute of information technology,  design and manufacturing, kurnool",
        "indian institute of information technology design & manufacturing kancheepuram",
        "indian institute of information technology, dharwad",
        "indian institute of information technology, guwahati",
        "indian institute of information technology, kalyani",
        "indian institute of information technology, kota",
        "indian institute of information technology, kottayam",
        "indian institute of information technology, lucknow",
        "indian institute of information technology, nagpur",
        "indian institute of information technology, pune",
        "indian institute of information technology, ranchi",
        "indian institute of information technology, senapati",
        "indian institute of information technology, sonepat",
        "indian institute of information technology, sri city, chittoor (iiit sri city (iiits))",
        "indian institute of information technology, tiruchirapalli",
        "indian institute of information technology, una (iiit, una)",
        "indian institute of information technology, vadodara",
        "indian institute of science, bangalore (iisc)",
        "indian institute of technology bhubaneswar",
        "indian institute of technology, bombay",
        "indian institute of technology, chennai",
        "indian institute of technology, delhi (iit delhi)",
        "indian institute of technology, dhanbad",
        "indian institute of technology dharwad",
        "indian institute of technology gandhinagar",
        "indian institute of technology goa (iit goa)",
        "indian institute of technology, guwahati (iitg)",
        "indian institute of technology hyderabad",
        "indian institute of technology (iit) bhilai",
        "indian institute of technology indore",
        "indian institute of technology jammu (iit jammu)",
        "indian institute of technology, kanpur (iit kanpur)",
        "indian institute of technology, kharagpur (iit kharagpur)",
        "indian institute of technology mandi (iit mandi)",
        "indian institute of technology palakkad",
        "indian institute of technology patna (iit patna or iitp)",
        "indian institute of technology punjab",
        "indian institute of technology rajasthan",
        "indian institute of technology roorkee (iit roorkee or iitr)",
        "indian institute of technology tirupati",
        "indian institute of technology varanasi",
        "indian law institute (ili), delhi",
        "indian statistical institute (isi), kolkata",
        "indraprastha institute of information technology, delhi",
        "institute of chemical technology (ict), mumbai",
        "institute of liver and biliary sciences (ilbs), new delhi",
        "international institute of information technology, bangalore",
        "jadavpur university, kolkata",
        "jain university, bangalore",
        "jain vishva bharati institute (jvbi), ladnun",
        "jamia hamdard, new delhi",
    ],
    "tier2": [
        "jamia millia islamia (jmi), new delhi",
        "academy of scientic & innovative research (acsir)",
        "acharya n g ranga agricultural university, hyderabad",
        "amity university, jaipur",
        "amity university, noida",
        "anand agricultural university",
        "atal bihari vajpayee hindi vishwavidyalaya, bhopal",
        "atal bihari vajpayee indian institute of information technology and management, gwalior (abv-iiitm gwalior)",
        "assam agricultural university, jorhat",
        "assam don bosco university",
        "assam university",
        "avinashilingam institute for home science and higher education for women",
        "awadhesh pratap singh university",
        "b.l.d.e university, bijapur",
        "babasaheb bhimrao ambedkar bihar university, muzaffarpur",
        "barkatullah university",
        "bengal engineering & science university",
        "bharat ratna dr b.r. ambedkar university, delhi",
        "fakir mohan university",
        "forest research institute (fri)",
        "footwear design & development institute",
        "gauhati university",
        "goa university, taleigao plateau",
        "graphic era university",
        "gujarat university, ahmedabad",
        "gulbarga university",
        "guru angad dev veterinary and animal sciences university (gadvasu)",
        "guru ghasidas vishwavidyalaya, bilaspur (ggu)",
        "gurukula kangri vishwavidyalaya, hardwar",
        "himachal pradesh board of technical education",
        "iftm university (institute of foreign trade and management)",
        "i.i.s. university",
        "i.k. gujral punjab technical university (ikgptu)",
        "indian maritime university (imu)",
        "indian institute of engineering science and technology, shibpur",
        "indian institute of science education and research bhopal",
        "indian institute of science education and research kolkata",
        "indian institute of science education and research pune",
        "indian institute of science education and research thiruvananthapuram",
        "indian institute of science education and research tirupati",
        "indian institute of science education & research (iiser) mohali",
        "indian veterinary research institute (ivri), izatnagar",
        "indira gandhi institute of development research (igidr), mumbai",
        "indira kala sangit vishwavidyalaya (iksv), khairagarh",
        "indira gandhi national open university (ignou)",
        "indira gandhi national tribal university, amarkantak",
        "integral university",
        "international institute for population sciences (iips)",
        "international institute of information technology",
        "islamic university of science and technology",
        "jagan nath university",
        "jai narain vyas university, jodhpur (jnvu)",
        "jaipur national university",
        "jawaharlal nehru technological university anantapur (jntu)",
        "jawaharlal nehru technological university kakinada (jntu kakinada)",
        "jaypee institute of information technology",
        "jaypee university of information technology",
        "junagadh agricultural university (jau)",
        "kalinga institute of industrial technology (kiit)",
        "kameshwar singh darbhanga sanskrit university (ksdsu)",
        "kannada university",
        "kumaun university",
        "kannur university",
        "karnataka state women's university",
        "karpagam academy of higher education",
        "kavikulguru kalidas sanskrit university (kksu)",
        "kerala agricultural university (kau)",
        "kuvempu university",
    ],
    "tier3": [
        "indian institute of teacher education (iite)",
        "indira gandhi delhi technical university for women (igdtuw)",
        "indira gandhi institute of medical sciences",
        "indira gandhi krishi vishwavidyalaya, raipur ((igkv)",
        "indira gandhi technological and medical science university (igtamsu)",
        "indira gandhi university",
        "indrashil university",
        "indus international university (iiu)",
        "indus university",
        "institute of advanced research (iar), gandhinagar",
        "institute of advanced studies in education (iase) deemed university",
        "institute of chartered financial analysts of india (icfai) university, dehradun",
        "institute of chartered financial analysts of india (icfai) university, dimapur",
        "institute of chartered financial analysts of india (icfai) university, gangtok, sikkim",
        "institute of trans-disciplinary health sciences and technology",
        "institute of infrastructure technology research and management (iitram)",
        "international institute of information technology, bhubaneswar",
    ],
}


def get_university_tier(university_name: str) -> str:
    name = university_name.lower().strip()
    for tier, universities in TIER_DATA.items():
        if name in [u.lower().strip() for u in universities]:
            return tier
    return "tier3"


# Summarization prompt
def summarize_resume_with_llm(resume_text) -> str:
    prompt = f"""You are an intelligent assistant that extracts structured, concise information from resumes to support job and internship matching.
            Given the following resume description, extract only the most relevant details and output a JSON in the format below. Ensure:
            - All text is in lowercase.
            - Convert any abbreviations or short forms to their full forms (e.g., "mern" → "mongo, express, react, node").
            - Be concise and avoid generic or repetitive content.
            - For "degree_qualification", extract only the latest education degree name (e.g: bachelor of technology,bachelor of engineering,bachelor of science) .
            - "branch" refers to the field of study, use the standard naming convention(e.g: computer science and engineering, electronics and communication engineering, information technology).
            - for start_year and passed_out_year search in dates key of latest education (e.g: 2021 - 2025 or 2021 - present)
            - If any field is missing or unknown, leave it empty or null.
            Return the JSON in this format:
            json:{{
            "skills": "",
            "degree_qualification": "",
            "college_name": "",
            "branch": "",
            "start_year": ,
            "passed_out_year": ,
            "location": "",
            "grade":
            }}
            Resume Description:{resume_text}"""
    response = chat.invoke(prompt)
    return response.content.strip()


# Store resume vector with version
def resume_vectorStore_withversion(student_id: UUID, version_id: UUID, db: Session):
    # Step 1: Ensure Qdrant collection exists
    if COLLECTION_NAME not in [
        col.name for col in qdrant_client.get_collections().collections
    ]:
        qdrant_client.recreate_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )

    # Step 3: Get personal_info record for the student
    personal_info = (
        db.query(PersonalInfo)
        .filter(
            PersonalInfo.student_id == student_id, PersonalInfo.version_id == version_id
        )
        .first()
    )
    if not personal_info:
        return {"error": "Personal info not found"}

    user_profile_id = personal_info.id
    location = personal_info.location or "Not mentioned"

    # Step 4: Fetch skills and education using user_profile_id
    skills = db.query(Skill).filter(Skill.user_id == user_profile_id).all()
    education = db.query(Education).filter(Education.user_id == user_profile_id).all()

    # Step 5: Format the resume data
    skills_text = ", ".join([skill.skill_name for skill in skills])
    qualifications = ", ".join(
        [
            f"{edu.degree or 'N/A'} in {edu.institution_name or 'N/A'} with grade {edu.grade} "
            f"started in {edu.start_date.year if edu.start_date else 'N/A'} "
            f"ending in {edu.end_date.year if edu.end_date else 'Present'}"
            for edu in education
        ]
    )

    combined_resume_data = (
        f"Skills: {skills_text}\nQualifications: {qualifications}\nLocation: {location}"
    )

    logger.info(f"Combined DB Resume Data: {combined_resume_data}")

    # Step 6: Summarize and encode
    summary = summarize_resume_with_llm(combined_resume_data)
    logger.info(f"LLM Summary: {summary}")

    match = re.search(r"json\s*(\{.*?\})\s*", summary, re.DOTALL)
    if match:
        json_str = match.group(1)
        resume_data = json.loads(json_str)
        if resume_data.get("passed_out_year") is None:
            resume_data["passed_out_year"] = 2025
        resume_data["college_type"] = get_university_tier(
            resume_data.get("college_name")
        )
        logger.info(f"JSON data: {resume_data}")
    else:
        print("No valid JSON found.")

    vector = embedding_model.encode(
        resume_data.get("skills"), normalize_embeddings=False
    )

    # # Step 7: Create Qdrant point and upsert

    point = PointStruct(
        id=str(version_id),
        vector=vector.tolist(),
        payload={"student_id": str(student_id), "summary": resume_data},
    )
    logger.info(f"Resume Points to store: {point}")

    qdrant_client.upsert(collection_name=COLLECTION_NAME, points=[point])

    return {
        "message": f"Resume data summarized and stored in vector DB for user {personal_info.full_name}",
        "summary": resume_data,
    }


def recommend_internships_withversions(student_id: UUID, version_id: UUID, db: Session):
    logger.info(f"Recommending internships for student_id: {student_id}")

    # Step 2: Fetch student's resume vector from Qdrant
    try:
        retrieved = qdrant_client.retrieve(
            collection_name=COLLECTION_NAME, ids=[str(version_id)], with_vectors=True
        )
        if not retrieved:
            logger.warning(f"No vector found for student_id={student_id}")
            return {str(student_id): []}

        resume_point = retrieved[0]
        student_vector = resume_point.vector
        logger.info(f"Retrieved vector for student_id={student_id}")

    except Exception as e:
        logger.exception(f"Error while retrieving student vector: {e}")
        return {"error": "Failed to retrieve vector"}

    # Step 3: Scroll all internship vectors
    try:
        all_internships, _ = qdrant_client.scroll(
            collection_name=INTERNSHIP_COLLECTION,
            with_vectors=True,
            with_payload=True,
            limit=10000,
        )
        logger.info(f"Retrieved {len(all_internships)} internships from Qdrant")
    except Exception as e:
        logger.exception(f"Failed to scroll internship vectors: {e}")
        return {"error": "Internship vector fetch failed"}

    # Step 4: Similarity check and existence validation
    matched_ids = []
    similarity_score = []
    for internship in all_internships:
        similarity = util.cos_sim(student_vector, internship.vector).item()
        if similarity >= SIMILARITY_THRESHOLD:
            # Check if internship exists in DB before appending
            internship_exists = (
                db.query(JobPosting).filter(JobPosting.job_id == internship.id).first()
            )
            if internship_exists:
                matched_ids.append(internship.id)
                similarity_score.append(round(similarity * 100, 2))
                logger.info(f"Internship_id: {internship.id} matched and exists in DB.")
            else:
                logger.warning(
                    f"Internship ID {internship.id} not found in PostgresDB. Skipping."
                )

    logger.info(f"Matched {len(matched_ids)} internships (all exist in DB)")

    # Step 5: Resume screening logging
    screening = (
        db.query(ResumeScreeningResult)
        .filter(
            ResumeScreeningResult.student_id == student_id,
            ResumeScreeningResult.version_id == version_id,
        )
        .order_by(
            ResumeScreeningResult.screened_at.desc()
            if hasattr(ResumeScreeningResult, "screened_at")
            else None
        )
        .first()
    )
    if screening:
        screening_id = screening.screening_id
        version_id = screening.version_id
        logger.info(f"Reusing existing screening_id: {screening_id}")
    else:
        # version = (
        #     db.query(ResumeVersion).filter(ResumeVersion.student_id == student_id).first()
        # )
        # version_id = version.version_id if version else uuid4()
        screening_id = uuid4()
        screening = ResumeScreeningResult(
            screening_id=screening_id,
            version_id=version_id,
            student_id=student_id,
            fitment_score=75.0,
            strengths=["Skills", "Qualifications"],
            gaps=["Project Experience"],
            is_qualified=True,
            persona_match_score=0.78,
        )
        db.add(screening)
        db.commit()
        logger.info(f"Screening result committed with ID: {screening_id}")

    # Step 6: Add matched internships to ResumeScreeningInternship (no need to check existence again)
    for i in range(len(matched_ids)):
        db.add(
            ResumeScreeningInternship(
                screening_id=screening_id,
                internship_id=matched_ids[i],
                ats_score=similarity_score[i],
                matching_reason=None,
                source="External",
            )
        )

    db.commit()
    logger.info("Screening and matched internships committed to DB.")

    return {
        "student_id": str(student_id),
        "screening_id": str(screening_id),
        "matched_internships": matched_ids,
    }


def recommend_internal_jobs_withversion(
    student_id: UUID, version_id: UUID, db: Session
):
    logger.info(
        f"Recommending internal jobs/internships for student_id: {student_id} and version_id: {version_id}"
    )

    # Step 2: Get latest screening_id for this student
    screening = (
        db.query(ResumeScreeningResult)
        .filter(
            ResumeScreeningResult.student_id == student_id,
            ResumeScreeningResult.version_id == version_id,
        )
        .order_by(ResumeScreeningResult.screened_at.desc())
        .first()
    )
    if not screening:
        logger.warning("No screening record found for student.")
        return {"error": "No screening record found"}

    screening_id = screening.screening_id

    # Step 3: Retrieve student's vector and payload from Qdrant
    try:
        retrieved = qdrant_client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=[str(version_id)],
            with_vectors=True,
            with_payload=True,
        )
        if not retrieved:
            logger.warning("No vector found for student")
            return {"error": "No vector found for student"}

        student_vector = retrieved[0].vector
        student_payload = retrieved[0].payload.get("summary", {})
        logger.info("Student vector and payload retrieved")

    except Exception as e:
        logger.exception(f"Error retrieving vector: {e}")
        return {"error": "Failed to retrieve student vector"}

    # Step 4: Get all internal job vectors
    try:
        all_jobs, _ = qdrant_client.scroll(
            collection_name=settings.JOB_COLLECTION_NAME,
            with_vectors=True,
            with_payload=True,
            limit=10000,
        )

        if not all_jobs:
            logger.warning("No job vectors found in Qdrant.")
            return {"message": "No jobs found in Qdrant."}

        logger.info(f"Retrieved {len(all_jobs)} job postings from Qdrant")
    except Exception as e:
        logger.exception(f"Failed to scroll internal job vectors: {e}")
        return {"error": "Failed to retrieve job vectors"}

    matched_ids = []
    similarity_scores = []
    matching_details = []

    for job in all_jobs:
        job_vector = job.vector
        job_payload = job.payload.get("summary", {})
        similarity = util.cos_sim(student_vector, job_vector).item()

        if similarity >= SIMILARITY_THRESHOLD:
            # Check payload fields match
            if check_payload_match(job_payload, student_payload):
                # Check if job exists in DB before appending
                job_exists = (
                    db.query(JobPosting).filter(JobPosting.job_id == job.id).first()
                )
                if job_exists:
                    matched_ids.append(job.id)
                    similarity_scores.append(round(similarity * 100, 2))
                    matching_details.append(extract_matching_fields(student_payload))
                    logger.info(
                        f"Job {job.id} matched with score {similarity} and exists in DB."
                    )
                else:
                    logger.warning(
                        f"JobPosting ID {job.id} not found in PostgresDB. Skipping."
                    )

    if not matched_ids:
        logger.info("No internal jobs matched.")
        return {"matched_internal_jobs": []}

    # Step 5: Insert into ResumeScreeningInternship and JobCandidateMatching
    for i in range(len(matched_ids)):
        job_id = matched_ids[i]
        score = similarity_scores[i]
        details = matching_details[i]

        # Insert into ResumeScreeningInternship (candidate-side)
        db.merge(
            ResumeScreeningInternship(
                screening_id=screening_id,
                internship_id=job_id,
                ats_score=score,
                matching_reason=None,
                source="Internal",
            )
        )

        # Employer-side: Find or create JobCandidateScreening for this job
        screening_obj = (
            db.query(JobCandidateScreening)
            .filter(JobCandidateScreening.job_id == job_id)
            .first()
        )
        if not screening_obj:
            # Create a new screening record for this job
            employer_id = (
                db.query(JobPosting)
                .filter(JobPosting.job_id == job_id)
                .first()
                .employer_id
            )
            screening_obj = JobCandidateScreening(
                screening_id=uuid4(), employer_id=employer_id, job_id=job_id
            )
            db.add(screening_obj)
            db.flush()  # To get screening_obj.screening_id

        # Insert into JobCandidateMatching (employer-side)
        db.merge(
            JobCandidateMatching(
                screening_id=screening_obj.screening_id,
                student_id=student_id,
                version_id=version_id,
                matching_reason=None,
                matching_score=score,
                degree_qualification=details.get("degree_qualification"),
                college_name=details.get("college_name"),
                branch=details.get("branch"),
                passed_out_year=details.get("passed_out_year"),
                grade=details.get("grade"),
                college_type=details.get("college_type"),
                location=details.get("location"),
            )
        )

    db.commit()
    logger.info(
        f"{len(matched_ids)} internal job matches committed to DB (candidate and employer side)."
    )

    return {
        "student_id": str(student_id),
        "version_id": str(version_id),
        "screening_id": str(screening_id),
        "matched_internal_jobs": matched_ids,
    }


def check_payload_match(job_payload, candidate_payload):
    fields = ["college_type", "branch", "passed_out_year", "grade"]
    for field in fields:
        job_value = job_payload.get(field)
        candidate_value = candidate_payload.get(field)
        if job_value is None or job_value == "":
            continue
        if field == "passed_out_year":
            if isinstance(job_value, list):
                if candidate_value not in job_value:
                    return False
            else:
                if candidate_value != job_value:
                    return False
        elif field == "grade":
            try:
                if float(candidate_value) < float(job_value):
                    return False
            except Exception:
                return False
        else:
            if isinstance(job_value, str) and isinstance(candidate_value, str):
                if job_value.lower() != candidate_value.lower():
                    return False
            else:
                if job_value != candidate_value:
                    return False
    return True


def extract_matching_fields(payload):
    # Adjust field names as per your payload structure
    return {
        "degree_qualification": payload.get("degree_qualification"),
        "college_name": payload.get("college_name"),
        "branch": payload.get("branch"),
        "passed_out_year": payload.get("passed_out_year"),
        "grade": payload.get("grade"),
        "college_type": payload.get("college_type"),
        "location": payload.get("location"),
    }


# to recommend internships for the resumes after new external internships are obtained via cron job
async def batch_resume_internship_matching(db: Session):
    logger.info("Starting batch resume-internship matching process.")

    # Fetch all resumes with vectors
    all_resumes, _ = qdrant_client.scroll(
        collection_name=COLLECTION_NAME,
        with_vectors=True,
        with_payload=True,
        limit=10000,
    )
    logger.info(f"Fetched {len(all_resumes)} resumes.")

    # Fetch all internships with vectors
    all_internships, _ = qdrant_client.scroll(
        collection_name=INTERNSHIP_COLLECTION,
        with_vectors=True,
        with_payload=True,
        limit=10000,
    )
    logger.info(f"Fetched {len(all_internships)} internships.")

    for resume in all_resumes:
        # student_id is the Qdrant point id
        student_id = resume.id
        if not student_id:
            logger.warning("No student_id found in resume point id. Skipping.")
            continue

        # Check if student_id exists in ResumeVersion table
        resume_version_exists = (
            db.query(ResumeVersion)
            .filter(ResumeVersion.student_id == student_id)
            .first()
        )
        if not resume_version_exists:
            logger.info(
                f"student_id {student_id} not found in ResumeVersion table. Skipping."
            )
            continue

        # Get screening_id for this student
        screening = (
            db.query(ResumeScreeningResult)
            .filter(ResumeScreeningResult.student_id == student_id)
            .first()
        )

        if not screening:
            # If not found, create a new ResumeScreeningResult
            version = (
                db.query(ResumeVersion)
                .filter(ResumeVersion.student_id == student_id)
                .first()
            )
            version_id = version.version_id if version else uuid4()
            screening_id = uuid4()
            new_screening = ResumeScreeningResult(
                screening_id=screening_id,
                version_id=version_id,
                student_id=student_id,
                fitment_score=75.0,
                strengths=["Skills", "Qualifications"],
                gaps=["Project Experience"],
                is_qualified=True,
                persona_match_score=0.78,
                # Add other required fields here as per your model
            )
            db.add(new_screening)
            db.flush()  # To get the screening_id if needed
            logger.info(
                f"Created new ResumeScreeningResult for student_id={student_id}"
            )
        else:
            screening_id = screening.screening_id

        # Get already matched internship_ids for this screening
        existing_matches = (
            db.query(ResumeScreeningInternship.internship_id)
            .filter(ResumeScreeningInternship.screening_id == screening_id)
            .all()
        )
        matched_internship_ids = set(row[0] for row in existing_matches)

        # For each internship not already matched, check similarity
        for internship in all_internships:
            internship_id = internship.id
            if internship_id in matched_internship_ids:
                continue  # Already matched

            similarity = util.cos_sim(resume.vector, internship.vector).item()
            if similarity >= SIMILARITY_THRESHOLD:
                db.add(
                    ResumeScreeningInternship(
                        screening_id=screening_id,
                        internship_id=internship_id,
                        ats_score=round(similarity * 100, 2),
                        matching_reason=None,
                        source="External",
                    )
                )
                logger.info(
                    f"Matched student_id={student_id} to internship_id={internship_id} with score={similarity:.2f}"
                )

        db.commit()
        logger.info(f"Committed matches for student_id={student_id}")

    logger.info("Batch resume-internship matching completed.")
    return {"status": "success"}


def delete_resume_vector_withversion(user_id: UUID, version_id: UUID, db: Session):
    # Step 1: Get student_id from user_id
    # student = db.query(Student).filter(Student.user_id == user_id).first()
    # if not student:
    #     return {"error": "Student not found"}

    # student_id = str(student.student_id)

    # Step 2: Retrieve the vector before deletion
    try:
        retrieved = qdrant_client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=[version_id],
            with_vectors=True,
            with_payload=True,
        )
        if not retrieved:
            return {"error": "No vector found for student"}
        # retrieved is a list of points; get the first (and only) point
        deleted_vector = {
            "vector": retrieved[0].vector,
            "payload": retrieved[0].payload,
        }
    except Exception as e:
        return {"error": f"Failed to retrieve vector: {e}"}

    # Step 3: Delete the vector from Qdrant
    try:
        qdrant_client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=models.PointIdsList(
                points=[version_id],  # student_id as str or int
            ),
        )
    except Exception as e:
        return {"error": f"Failed to delete vector: {e}"}

    # Step 4: Return the deleted vector
    return {
        "message": f"Deleted resume vector for user_id={user_id}",
        "deleted_vector": deleted_vector,
    }
