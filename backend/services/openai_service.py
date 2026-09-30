import os
from openai import OpenAI

client = None
_cached_api_key = None

# Available models
OPENAI_MODELS = {
    "gpt-4o-mini": "GPT-4o Mini (Fast, Cheap)",
    "gpt-4o": "GPT-4o (Best Quality)",
    "gpt-4-turbo": "GPT-4 Turbo (High Quality)",
}
DEFAULT_MODEL = "gpt-4o-mini"


def get_db_setting(key: str, default: str = None) -> str:
    """Get a setting from the database."""
    try:
        from database import SessionLocal
        from models import AppSetting
        db = SessionLocal()
        try:
            setting = db.query(AppSetting).filter(AppSetting.key == key).first()
            if setting:
                return setting.value
        finally:
            db.close()
    except Exception:
        pass
    return default


def get_ai_model() -> str:
    """Get the configured AI model from database."""
    model = get_db_setting("ai_model", DEFAULT_MODEL)
    if model in OPENAI_MODELS:
        return model
    return DEFAULT_MODEL


def get_openai_api_key():
    """Get OpenAI API key from environment or database."""
    # Check environment first
    env_key = os.environ.get("OPENAI_API_KEY")
    if env_key:
        return env_key

    # Check database
    return get_db_setting("openai_api_key")


def get_client():
    global client, _cached_api_key

    api_key = get_openai_api_key()
    if not api_key:
        raise ValueError("OpenAI API key not configured. Set it in Settings or via OPENAI_API_KEY environment variable.")

    # Recreate client if API key changed
    if client is None or _cached_api_key != api_key:
        client = OpenAI(api_key=api_key)
        _cached_api_key = api_key

    return client


def generate_cover_letter(job_title: str, company_name: str, job_description: str, resume_text: str) -> str:
    """Generate a tailored cover letter for a specific job."""
    from datetime import datetime
    openai_client = get_client()

    today_date = datetime.now().strftime("%B %d, %Y")

    prompt = f"""Write a professional cover letter for the following job application.

Job Title: {job_title}
Company: {company_name}
Today's Date: {today_date}

Job Description:
{job_description}

Candidate's Resume/Background:
{resume_text}

CRITICAL INSTRUCTIONS:
1. Extract the candidate's ACTUAL name, email, phone number, and location from their resume above
2. Use the ACTUAL extracted information in the letter header - DO NOT use placeholders like [Your Name]
3. Use today's date: {today_date}
4. For the company address, just use "{company_name}" as the recipient (no street address needed)
5. Write a compelling cover letter highlighting relevant skills from the resume
6. Keep it concise (3-4 paragraphs)
7. Sign with the candidate's ACTUAL name from the resume

Format the letter header as:
[Candidate's actual name from resume]
[Their actual location from resume]
[Their actual email from resume]
[Their actual phone from resume]

{today_date}

Hiring Manager
{company_name}

Dear Hiring Manager,

[Letter body...]

Sincerely,
[Candidate's actual name]
"""

    response = openai_client.chat.completions.create(
        model=get_ai_model(),
        messages=[
            {"role": "system", "content": "You are an expert career coach who writes compelling, personalized cover letters that help candidates stand out."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=1000
    )

    return response.choices[0].message.content


def generate_interview_questions(job_title: str, job_description: str, interview_type: str) -> str:
    """Generate practice interview questions based on the job."""
    openai_client = get_client()

    type_guidance = {
        "phone_screen": "Focus on general fit questions, basic qualifications, and motivation for the role.",
        "technical": "Focus on technical skills, problem-solving, coding concepts, and system design relevant to the role.",
        "behavioral": "Focus on STAR method questions about past experiences, teamwork, leadership, and conflict resolution.",
        "onsite": "Mix of technical depth, cultural fit, and scenario-based questions.",
        "final": "Focus on leadership, long-term goals, company culture fit, and strategic thinking."
    }

    guidance = type_guidance.get(interview_type, "Mix of behavioral and technical questions.")

    prompt = f"""Generate interview practice questions for the following job.

Job Title: {job_title}
Interview Type: {interview_type}

Job Description:
{job_description}

Interview Focus: {guidance}

Instructions:
- Generate 10-12 likely interview questions
- For each question, provide a brief tip on how to approach the answer
- Include a mix of difficulty levels
- Make questions specific to the job description when possible
- Format as a numbered list with the question followed by the tip
"""

    response = openai_client.chat.completions.create(
        model=get_ai_model(),
        messages=[
            {"role": "system", "content": "You are an experienced hiring manager and interview coach who helps candidates prepare for job interviews."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=1500
    )

    return response.choices[0].message.content


def analyze_resume_job_match(job_description: str, resume_text: str) -> dict:
    """Analyze how well a resume matches a job posting."""
    openai_client = get_client()

    prompt = f"""Analyze how well this resume matches the job description.

Job Description:
{job_description}

Resume:
{resume_text}

Provide your analysis in the following exact format:

MATCH SCORE: [number 0-100]

MATCHING SKILLS:
- [skill 1]
- [skill 2]
(list all matching skills/keywords found)

MISSING SKILLS:
- [skill 1]
- [skill 2]
(list important skills from job description not found in resume)

RECOMMENDATIONS:
- [recommendation 1]
- [recommendation 2]
(specific suggestions to improve the match)

SUMMARY:
[2-3 sentence overall assessment]
"""

    response = openai_client.chat.completions.create(
        model=get_ai_model(),
        messages=[
            {"role": "system", "content": "You are an expert ATS (Applicant Tracking System) analyst and career coach who helps candidates optimize their resumes for specific jobs."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=1000
    )

    content = response.choices[0].message.content

    # Parse the response
    result = {
        "raw_analysis": content,
        "match_score": 0,
        "matching_skills": [],
        "missing_skills": [],
        "recommendations": [],
        "summary": ""
    }

    lines = content.split('\n')
    current_section = None

    for line in lines:
        line = line.strip()
        if line.startswith("MATCH SCORE:"):
            try:
                score_text = line.replace("MATCH SCORE:", "").strip()
                score_text = ''.join(c for c in score_text if c.isdigit())
                result["match_score"] = int(score_text) if score_text else 0
            except ValueError:
                result["match_score"] = 0
        elif line.startswith("MATCHING SKILLS:"):
            current_section = "matching_skills"
        elif line.startswith("MISSING SKILLS:"):
            current_section = "missing_skills"
        elif line.startswith("RECOMMENDATIONS:"):
            current_section = "recommendations"
        elif line.startswith("SUMMARY:"):
            current_section = "summary"
        elif line.startswith("- ") and current_section in ["matching_skills", "missing_skills", "recommendations"]:
            result[current_section].append(line[2:])
        elif current_section == "summary" and line:
            result["summary"] += line + " "

    result["summary"] = result["summary"].strip()

    return result


def generate_company_research(company_name: str, industry: str = None, website: str = None) -> str:
    """Generate a company research summary for interview prep."""
    openai_client = get_client()

    context = f"Company: {company_name}"
    if industry:
        context += f"\nIndustry: {industry}"
    if website:
        context += f"\nWebsite: {website}"

    prompt = f"""Generate an interview preparation research brief for this company.

{context}

Create a comprehensive but concise research summary including:

1. COMPANY OVERVIEW
- What the company does
- Key products/services
- Company size and market position (if well-known)

2. COMPANY CULTURE & VALUES
- Known cultural aspects
- Mission/values (if well-known)
- Work environment reputation

3. RECENT NEWS & TRENDS
- Topics the company might be focused on
- Industry trends affecting them
- Potential challenges or opportunities

4. INTERVIEW TALKING POINTS
- Topics that might impress interviewers
- Ways to show you've done your research
- Questions that demonstrate genuine interest

5. QUESTIONS TO ASK THE INTERVIEWER
- Thoughtful questions about the company
- Questions about team and role
- Questions about growth and future

Note: Base this on general knowledge. For the most current information, the candidate should also check the company's website and recent news.
"""

    response = openai_client.chat.completions.create(
        model=get_ai_model(),
        messages=[
            {"role": "system", "content": "You are a career coach helping candidates prepare for interviews by researching companies. Provide helpful, accurate information based on general knowledge about well-known companies, and general industry insights for less known companies."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=1500
    )

    return response.choices[0].message.content


def generate_ats_tailored_resume(resume_text: str, job_title: str, job_description: str, company_name: str = None) -> str:
    """Generate an ATS-optimized resume tailored to a specific job."""
    openai_client = get_client()

    company_context = f" at {company_name}" if company_name else ""

    prompt = f"""You are an expert ATS (Applicant Tracking System) resume optimizer. Rewrite the candidate's resume to be highly optimized for the following job posting.

Job Title: {job_title}{company_context}

Job Description:
{job_description}

Original Resume:
{resume_text}

Instructions:
1. KEYWORD OPTIMIZATION: Incorporate exact keywords and phrases from the job description naturally throughout the resume
2. SKILLS ALIGNMENT: Reorganize and emphasize skills that directly match the job requirements
3. EXPERIENCE TAILORING: Rewrite bullet points to highlight relevant accomplishments that match the job duties
4. QUANTIFIABLE ACHIEVEMENTS: Ensure metrics and numbers are included where possible
5. FORMAT: Use a clean, ATS-friendly format with clear section headers (SUMMARY, EXPERIENCE, SKILLS, EDUCATION)
6. RELEVANCE: Prioritize and expand on experiences most relevant to this specific role
7. ACTION VERBS: Use strong action verbs that match the job description language

Output the complete rewritten resume in a clean, professional format. Do not include any commentary - just output the optimized resume text ready to be used.
"""

    response = openai_client.chat.completions.create(
        model=get_ai_model(),
        messages=[
            {"role": "system", "content": "You are a professional resume writer specializing in ATS optimization. You transform resumes to maximize their chances of passing ATS screening and impressing recruiters for specific job postings."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.5,
        max_tokens=3000
    )

    return response.choices[0].message.content


def complete_text(system: str, prompt: str, max_tokens: int = 1000) -> str:
    """Single-turn completion with the configured model."""
    openai_client = get_client()
    response = openai_client.chat.completions.create(
        model=get_ai_model(),
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""
