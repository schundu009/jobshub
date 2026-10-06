import os
from contextvars import ContextVar
import logging

import openai
from openai import OpenAI

logger = logging.getLogger(__name__)

client = None
_cached_api_key = None

# Selectable models (admin Settings > AI model). Verified on the production key 2026-10-05.
OPENAI_MODELS = {
    "gpt-5.4-mini": "GPT-5.4 Mini (Default)",
    "gpt-5.6-luna": "GPT-5.6 Luna (Cheap, Auto Apply drafting)",
    "gpt-6-luna": "GPT-6 Luna (Newest efficient, cheapest)",
    "gpt-6.1-sol": "GPT-6.1 Sol (Near-Astra, mid price)",
    "gpt-6-astra": "GPT-6 Astra (Most capable, priciest)",
}
DEFAULT_MODEL = "gpt-5.4-mini"

# Per-feature model map: the one place that decides which OpenAI model a feature uses.
# Features listed here use a fixed model; every other feature uses the admin's
# "ai_model" setting, else DEFAULT_MODEL.
FEATURE_MODELS = {
    "auto_apply_draft": "gpt-5.6-luna",  # high volume, short answers
}

# Another OpenAI-compatible provider this call runs on (compat_service.py):
# {"client", "model", "headroom"}. Unset, calls use OpenAI and the settings.
_bound = ContextVar("openai_compat_target", default=None)

# GPT-5.x may spend completion tokens on reasoning before any visible text, so a
# max_completion_tokens equal to the old max_tokens could return an empty answer.
_REASONING_HEADROOM = 2048


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


def get_ai_model(feature: str = None) -> str:
    """Model for a feature: FEATURE_MODELS, else the admin's ai_model setting, else DEFAULT_MODEL.

    A saved id that is no longer offered (e.g. a retired gpt-4o) falls back to DEFAULT_MODEL.
    """
    bound = _bound.get()
    if bound:
        return bound["model"]
    if feature in FEATURE_MODELS:
        return FEATURE_MODELS[feature]
    model = get_db_setting("ai_model", DEFAULT_MODEL)
    if model in OPENAI_MODELS:
        return model
    return DEFAULT_MODEL


def _is_reasoning_model(model: str) -> bool:
    """GPT-5.x, GPT-6.x and o-series: max_completion_tokens only, default temperature only."""
    return model.startswith(("gpt-5", "gpt-6", "o1", "o3", "o4"))


def _chat(model: str, messages: list, max_tokens: int, temperature: float = None) -> str:
    """chat.completions.create with the parameters the model family accepts.

    GPT-5.x rejects max_tokens (needs max_completion_tokens) and non-default
    temperature. If the API still rejects one of them, retry once without it.
    """
    kwargs = {"model": model, "messages": messages}
    bound = _bound.get()
    if bound and bound.get("headroom"):
        # Thinking models count their reasoning against max_tokens.
        max_tokens = max_tokens + bound["headroom"]
    if _is_reasoning_model(model):
        kwargs["max_completion_tokens"] = max_tokens + _REASONING_HEADROOM
    else:
        kwargs["max_tokens"] = max_tokens
        if temperature is not None:
            kwargs["temperature"] = temperature

    openai_client = get_client()
    try:
        response = openai_client.chat.completions.create(**kwargs)
    except openai.BadRequestError as e:
        message = str(e)
        retry = dict(kwargs)
        if "temperature" in message and "temperature" in retry:
            retry.pop("temperature")
        if "max_tokens" in message and "max_tokens" in retry:
            retry["max_completion_tokens"] = retry.pop("max_tokens") + _REASONING_HEADROOM
        if retry == kwargs:
            raise
        logger.warning("OpenAI rejected parameters for %s (%s); retrying without them", model, message)
        response = openai_client.chat.completions.create(**retry)
    return response.choices[0].message.content or ""


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

    bound = _bound.get()
    if bound:
        return bound["client"]

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

    return _chat(
        get_ai_model(),
        [
            {"role": "system", "content": "You are an expert career coach who writes compelling, personalized cover letters that help candidates stand out."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=1000,
        temperature=0.7,
    )


def generate_interview_questions(job_title: str, job_description: str, interview_type: str) -> str:
    """Generate practice interview questions based on the job."""
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

    return _chat(
        get_ai_model(),
        [
            {"role": "system", "content": "You are an experienced hiring manager and interview coach who helps candidates prepare for job interviews."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=1500,
        temperature=0.7,
    )


def analyze_resume_job_match(job_description: str, resume_text: str) -> dict:
    """Analyze how well a resume matches a job posting."""
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

    content = _chat(
        get_ai_model(),
        [
            {"role": "system", "content": "You are an expert ATS (Applicant Tracking System) analyst and career coach who helps candidates optimize their resumes for specific jobs."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=1000,
        temperature=0.3,
    )

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

    return _chat(
        get_ai_model(),
        [
            {"role": "system", "content": "You are a career coach helping candidates prepare for interviews by researching companies. Provide helpful, accurate information based on general knowledge about well-known companies, and general industry insights for less known companies."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=1500,
        temperature=0.7,
    )


def generate_ats_tailored_resume(resume_text: str, job_title: str, job_description: str, company_name: str = None) -> str:
    """Generate an ATS-optimized resume tailored to a specific job."""
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

    return _chat(
        get_ai_model(),
        [
            {"role": "system", "content": "You are a professional resume writer specializing in ATS optimization. You transform resumes to maximize their chances of passing ATS screening and impressing recruiters for specific job postings."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=3000,
        temperature=0.5,
    )


def complete_text(system: str, prompt: str, max_tokens: int = 1000, feature: str = None) -> str:
    """Single-turn completion on the feature's model (see FEATURE_MODELS)."""
    return _chat(
        get_ai_model(feature),
        [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.3,
    )
