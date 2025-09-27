
-- FINAL ENHANCED POSTGRESQL SCHEMA FOR INTERNHIRE PLATFORM
-- Includes ATS scoring, resume uplifting, JSON-based interview feedback, and complete intern hiring modules

-- ========================= USERS ============================
CREATE TABLE users (
    user_id UUID PRIMARY KEY,
    email VARCHAR(100) UNIQUE NOT NULL,
	full_name VARCHAR(100),
    password_hash TEXT NOT NULL,
    role VARCHAR(20) CHECK (role IN ('Student', 'Employer', 'Admin')),
    created_at TIMESTAMP DEFAULT NOW()
);

-- ========================= STUDENTS =========================
CREATE TABLE students (
    student_id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(user_id) ON DELETE CASCADE,
    email VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ========================= EMPLOYERS ========================
CREATE TABLE employer_profiles (
    employer_id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(user_id) ON DELETE CASCADE,
    company_name VARCHAR(150),
    company_type VARCHAR(50) CHECK (company_type IN ('Startup', 'Midsize', 'MNC')),
    company_description TEXT,
    logo_url TEXT,
    website_url TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ========================= COMPANIES ========================
CREATE TABLE companies (
    company_id UUID PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    type VARCHAR(50) CHECK (type IN ('Startup', 'Midsize', 'MNC')),
    location VARCHAR(100),
    description TEXT
);

-- ========================= INTERNSHIPS ======================
CREATE TABLE internships (
    internship_id UUID PRIMARY KEY,
    employer_id UUID REFERENCES companies(company_id),
	company_name TEXT, -- used only if employer_id is NULL
    title TEXT NOT NULL,
    description TEXT,
    location TEXT,
    type VARCHAR(100),
    source VARCHAR(50),
    stipend Text,
    category VARCHAR(100),
    role VARCHAR(100),
    skills_required TEXT[],
    requirements Text,
    responsibilities Text,
    application_deadline DATE,
    additional_info JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- ========================= JOB POSTINGS =====================
CREATE TABLE job_postings (
    job_id UUID PRIMARY KEY,
    employer_id UUID REFERENCES employer_profiles(employer_id) ON DELETE CASCADE,
	company_name TEXT, -- used only if employer_id is NULL
    title VARCHAR(150),
    description TEXT,
    location VARCHAR(100),
    job_type VARCHAR(20) CHECK (job_type IN ('Full-Time', 'Internship', 'Contract', 'Part-Time')),
    category VARCHAR(100),
    required_skills TEXT[],
    min_experience INT,
    salary_range TEXT,
    application_deadline DATE,
	additional_info JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    posted_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE job_applications (
    application_id UUID PRIMARY KEY,
    job_id UUID REFERENCES job_postings(job_id) ON DELETE CASCADE,
    student_id UUID REFERENCES students(student_id) ON DELETE CASCADE,
    status VARCHAR(20) CHECK (status IN ('Applied', 'Shortlisted', 'Rejected', 'Interviewed', 'Hired', 'Offered')),
    applied_on TIMESTAMP DEFAULT NOW(),
    current_stage VARCHAR(50),
    fitment_score FLOAT,
    last_updated TIMESTAMP DEFAULT NOW()
);

-- ========================= COURSES ==========================
CREATE TABLE courses (
    course_id UUID PRIMARY KEY,
    title VARCHAR(150) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    level VARCHAR(20) CHECK (level IN ('Beginner', 'Intermediate', 'Advanced')),
    duration VARCHAR(50),
    url TEXT
);

CREATE TABLE student_course_progress (
    student_id UUID REFERENCES students(student_id) ON DELETE CASCADE,
    course_id UUID REFERENCES courses(course_id) ON DELETE CASCADE,
    status VARCHAR(20) CHECK (status IN ('Not Started', 'In Progress', 'Completed')) DEFAULT 'Not Started',
    progress_percent INT DEFAULT 0,
    last_accessed TIMESTAMP,
    PRIMARY KEY (student_id, course_id)
);

-- ========================= ASPIRATIONS =========================
CREATE TABLE aspirations (
    aspiration_id UUID PRIMARY KEY,
    student_id UUID NOT NULL,
    aspiration_text TEXT NOT NULL
);


-- ========================= ROADMAPS =========================
CREATE TABLE roadmaps (
    roadmap_id UUID PRIMARY KEY,
    student_id UUID REFERENCES students(student_id) ON DELETE CASCADE,
    role VARCHAR(100),
    data JSONB
);

CREATE TABLE student_roadmap_progress (
    student_id UUID REFERENCES students(student_id) ON DELETE CASCADE,
    roadmap_id UUID REFERENCES roadmaps(roadmap_id) ON DELETE CASCADE,
    status VARCHAR(20) CHECK (status IN ('Not Started', 'In Progress', 'Completed')) DEFAULT 'Not Started',
    progress_percent INT DEFAULT 0,
    followed_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (student_id, roadmap_id)
);

-- ========================= INTERVIEWS =======================
CREATE TABLE interview_sessions (
    session_id UUID PRIMARY KEY,
    student_id UUID REFERENCES students(student_id) ON DELETE CASCADE,
    role VARCHAR(100),
    questions JSONB,
    responses JSONB,
    audio_link TEXT,
    is_video_enabled BOOLEAN DEFAULT FALSE,
    score FLOAT,
    feedback JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TYPE feedback_type_enum AS ENUM ('L1', 'MOCK');

CREATE TABLE interview_feedback (
    feedback_id UUID PRIMARY KEY,
    job_id UUID DEFAULT gen_random_uuid() REFERENCES job_postings(job_id) ON DELETE CASCADE,
    session_id UUID REFERENCES interview_sessions(session_id) ON DELETE CASCADE,
    feedback_summary TEXT,
    strengths_of_candidate TEXT[],
    areas_of_improvement TEXT[],
    overall_score_out_of_10 FLOAT,
    skill_recommendations TEXT[],
    feedback_type feedback_type_enum NOT NULL,
    submitted_at TIMESTAMP DEFAULT NOW(),
    learning_path jsonb,
);

CREATE TABLE interview_question_responses (
    response_id UUID PRIMARY KEY,
    session_id UUID REFERENCES interview_sessions(session_id) ON DELETE CASCADE,
    question_id VARCHAR,
    question TEXT,
    user_answer TEXT,
    individual_analysis TEXT,
    individual_score FLOAT,
    reason_for_score_given TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);


CREATE TABLE interview_termination_logs (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES interview_sessions(session_id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    reason VARCHAR(255) NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW() NOT NULL
);

-- ========================= RESUMES ==========================
CREATE TABLE resume_templates (
    template_id UUID PRIMARY KEY,
    name VARCHAR(100),
    preview_url TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE resume_versions (
    version_id UUID PRIMARY KEY,
    student_id UUID REFERENCES students(student_id) ON DELETE CASCADE,
    resume_type VARCHAR(20) CHECK (resume_type IN ('Uploaded', 'Uplifted')) NOT NULL,
    source_resume_id UUID,
    ats_score FLOAT CHECK (ats_score BETWEEN 0 AND 100),
    template_id UUID REFERENCES resume_templates(template_id),
    file BYTEA,
    file_path TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- ========================= SCREENING & INSIGHTS =============

CREATE TABLE resume_screening_results (
    screening_id UUID PRIMARY KEY,
	version_id UUID REFERENCES resume_versions(version_id) ON DELETE CASCADE,
    student_id UUID REFERENCES students(student_id) ON DELETE CASCADE,
    fitment_score FLOAT CHECK (fitment_score BETWEEN 0 AND 100),
    strengths TEXT[],
    gaps TEXT[],
    is_qualified BOOLEAN,
    persona_match_score FLOAT,
    screened_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE student_insights (
    insight_id UUID PRIMARY KEY,
    student_id UUID REFERENCES students(student_id) ON DELETE CASCADE,
    recommended_roles TEXT[],
    most_matched_skills TEXT[],
    skill_gap_areas TEXT[],
    learning_recommendations TEXT[],
    engagement_score FLOAT,
    last_updated TIMESTAMP DEFAULT NOW()
);

CREATE TABLE resume_screening_internship (
    screening_id UUID REFERENCES resume_screening_results(screening_id) ON DELETE CASCADE,
    internship_id UUID REFERENCES internships(internship_id) ON DELETE CASCADE,
    ats_score FLOAT,
    matching_reason TEXT,
    PRIMARY KEY (screening_id, internship_id)
);

-- ========================= RESUME EXTRACTION ==========================

CREATE TABLE personal_info (
    id UUID PRIMARY KEY,
	version_id UUID REFERENCES resume_versions(version_id) ON DELETE CASCADE,
    student_id UUID REFERENCES students(student_id) ON DELETE CASCADE,
    full_name VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(50),
    location VARCHAR(255),
    bio TEXT
);

CREATE TABLE company_experience (
    id UUID PRIMARY KEY,
    user_id INTEGER REFERENCES personal_info(id),
    company_name VARCHAR(255),
    your_position VARCHAR(255),
    company_website VARCHAR(255),
    company_location VARCHAR(255),
    company_description TEXT,
    company_logo TEXT
);


CREATE TABLE skills (
    id UUID PRIMARY KEY,
    user_id INTEGER REFERENCES personal_info(id),
    skill_name VARCHAR(255)
);

CREATE TABLE work_experience (
    id UUID PRIMARY KEY,
    company_id INTEGER REFERENCES company_experience(id),
    position_title VARCHAR(255),
    company_name VARCHAR(255),
    duration VARCHAR(100),
    description TEXT
);

CREATE TABLE certifications (
    id UUID PRIMARY KEY,
    user_id INTEGER REFERENCES personal_info(id),
    certification_name VARCHAR(255),
    issued_by VARCHAR(255),
    issue_date DATE,
    expiration_date DATE
);

CREATE TABLE social_profiles (
    id UUID PRIMARY KEY,
    user_id INTEGER REFERENCES personal_info(id),
    personal_website VARCHAR(255),
    linkedin VARCHAR(255),
    github VARCHAR(255),
    twitter VARCHAR(255)
);

CREATE TABLE education (
    id UUID PRIMARY KEY,
    user_id INTEGER REFERENCES personal_info(id),
    institution_name VARCHAR(255),
    degree VARCHAR(255),
    field_of_study VARCHAR(255),
    start_date DATE,
    end_date DATE,
    grade VARCHAR(50),
    description TEXT
);

CREATE TABLE languages (
    id UUID PRIMARY KEY,
    user_id INTEGER REFERENCES personal_info(id),
    language_name VARCHAR(100),
    proficiency_level VARCHAR(100)
);


-- ========================= HACKATHONS ========================
CREATE TABLE hackathons (
    id UUID PRIMARY KEY,
    employer_id UUID REFERENCES employer_profiles(employer_id) ON DELETE CASCADE,
    name VARCHAR NOT NULL,
    description TEXT,
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    registration_deadline TIMESTAMP NOT NULL,
    mode VARCHAR NOT NULL,
    theme VARCHAR,
    eligibility_criteria TEXT,
    min_team_size INTEGER NOT NULL,
    max_team_size INTEGER NOT NULL,
    submission_guidelines TEXT,
    rules VARCHAR[] NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    timeline JSON,
    status VARCHAR DEFAULT 'Upcoming'
);

CREATE TABLE problem_statements (
    id UUID PRIMARY KEY,
    hackathon_id UUID NOT NULL REFERENCES hackathons(id) ON DELETE CASCADE,
    title VARCHAR NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE hackathon_registrations (
    id UUID PRIMARY KEY,
    team_id UUID  NOT NULL REFERENCES team(team_id) ON DELETE CASCADE,
    hackathon_id UUID NOT NULL REFERENCES hackathons(id),
    team_name VARCHAR NOT NULL,
    college_name VARCHAR NOT NULL,
    has_teammates BOOLEAN DEFAULT FALSE,
    teammates JSON DEFAULT '[]',
    agreed_to_eligibility BOOLEAN DEFAULT FALSE
);

CREATE TABLE team (
    team_id UUID PRIMARY KEY,
    team_name VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE team_student (
    team_id UUID REFERENCES team(team_id) ON DELETE CASCADE,
    student_id UUID REFERENCES student(student_id) ON DELETE CASCADE,
    PRIMARY KEY (team_id, student_id)
);

CREATE TABLE aspirations (
    aspiration_id UUID PRIMARY KEY,
    student_id UUID NOT NULL,
    aspiration_text TEXT NOT NULL
);
 



-- ========================= SENTIMENT ANALYSIS ========================

CREATE TYPE sentiment_label_enum AS ENUM ('positive', 'neutral', 'negative');

CREATE TABLE interview_feedback_sentiment (
    sentiment_id UUID PRIMARY KEY,
    feedback_id UUID NOT NULL,
    session_id UUID NOT NULL,
    job_id UUID,
    student_id UUID NOT NULL,
    sentiment sentiment_label_enum NOT NULL,
    sentiment_score FLOAT[] NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT fk_feedback FOREIGN KEY (feedback_id) REFERENCES interview_experience_feedback(feedback_id) ON DELETE CASCADE,
    CONSTRAINT fk_session FOREIGN KEY (session_id) REFERENCES interview_sessions(session_id) ON DELETE CASCADE,
    CONSTRAINT fk_job FOREIGN KEY (job_id) REFERENCES job_postings(job_id) ON DELETE SET NULL,
    CONSTRAINT fk_student FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE
);

-- ========================= OFFER LETTERS ========================


CREATE TYPE letter_status AS ENUM ('Unsigned', 'Signed');

CREATE TABLE offer_letter_templates (
    template_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_file TEXT NOT NULL
);

CREATE TABLE offer_letters (
    letter_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id UUID REFERENCES students(student_id) ON DELETE CASCADE,
    job_id UUID REFERENCES job_postings(job_id) ON DELETE CASCADE,
    letter_file TEXT NOT NULL,
    status letter_status NOT NULL DEFAULT 'Unsigned',
    offered_on TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- ============================= BOOKMARKS ==========================

CREATE TABLE bookmark (
    bookmark_id UUID PRIMARY KEY,
    job_id UUID REFERENCES job_postings(job_id) ON DELETE CASCADE,
    student_id UUID REFERENCES student(student_id) ON DELETE CASCADE,
    );