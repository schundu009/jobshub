"""
Anthropic Claude AI service for job-related AI features.
Mirrors the functionality in openai_service.py but uses Claude models.
"""
import os
import anthropic

client = None
_cached_api_key = None

# Available Claude models
CLAUDE_MODELS = {
    "claude-opus-5-5": "Claude Opus 5.5 (Most Capable)",
    "claude-sonnet-5-5": "Claude Sonnet 5.5 (Best)",
    "claude-haiku-4-5-20251001": "Claude Haiku 4.5 (Fast)",
}
DEFAULT_MODEL = "claude-sonnet-5-5"

# Retired model ids (e.g. a stale AppSetting "claude_model") -> closest current model,
# so an old saved setting doesn't turn every request into a provider 404.
_LEGACY_MODEL_PREFIXES = (
    ("claude-3-opus", "claude-opus-5-5"),
    ("claude-3-5-haiku", "claude-haiku-4-5-20251001"),
    ("claude-3-haiku", "claude-haiku-4-5-20251001"),
    ("claude-3-5-sonnet", "claude-sonnet-5-5"),
    ("claude-3-7-sonnet", "claude-sonnet-5-5"),
    ("claude-3", "claude-sonnet-5-5"),
)

_logged_model_errors = set()


def resolve_claude_model(model: str) -> str:
    """Map a configured model id to a currently supported one."""
    if model in CLAUDE_MODELS:
        return model
    for prefix, replacement in _LEGACY_MODEL_PREFIXES:
        if model and model.startswith(prefix):
            return replacement
    return DEFAULT_MODEL


def _create_message(anthropic_client, **kwargs):
    """messages.create with a single clear log line when the model id 404s."""
    try:
        return anthropic_client.messages.create(**kwargs)
    except anthropic.NotFoundError as e:
        model = kwargs.get("model")
        if model not in _logged_model_errors:
            _logged_model_errors.add(model)
            import logging
            logging.getLogger(__name__).error(
                "Anthropic model %r not found (404) - it may be retired. "
                "Update the 'claude_model' setting or DEFAULT_MODEL. Provider said: %s",
                model, e,
            )
        raise


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


def get_claude_model() -> str:
    """Get the configured Claude model from database."""
    model = get_db_setting("claude_model", DEFAULT_MODEL)
    return resolve_claude_model(model)


def get_anthropic_api_key():
    """Get Anthropic API key from environment or database."""
    # Check environment first
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        return env_key

    # Check database
    return get_db_setting("anthropic_api_key")


def get_client():
    global client, _cached_api_key

    api_key = get_anthropic_api_key()
    if not api_key:
        raise ValueError("Anthropic API key not configured. Set it in Settings or via ANTHROPIC_API_KEY environment variable.")

    # Recreate client if API key changed
    if client is None or _cached_api_key != api_key:
        client = anthropic.Anthropic(api_key=api_key)
        _cached_api_key = api_key

    return client


def generate_cover_letter(job_title: str, company_name: str, job_description: str, resume_text: str) -> str:
    """Generate a tailored cover letter for a specific job."""
    from datetime import datetime
    anthropic_client = get_client()

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

    response = _create_message(anthropic_client, 
        model=get_claude_model(),
        max_tokens=1000,
        messages=[
            {"role": "user", "content": prompt}
        ],
        system="You are an expert career coach who writes compelling, personalized cover letters that help candidates stand out."
    )

    return response.content[0].text


def generate_interview_questions(job_title: str, job_description: str, interview_type: str) -> str:
    """Generate practice interview questions based on the job."""
    anthropic_client = get_client()

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

    response = _create_message(anthropic_client, 
        model=get_claude_model(),
        max_tokens=1500,
        messages=[
            {"role": "user", "content": prompt}
        ],
        system="You are an experienced hiring manager and interview coach who helps candidates prepare for job interviews."
    )

    return response.content[0].text


def analyze_resume_job_match(job_description: str, resume_text: str) -> dict:
    """Analyze how well a resume matches a job posting."""
    anthropic_client = get_client()

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

    response = _create_message(anthropic_client, 
        model=get_claude_model(),
        max_tokens=1000,
        messages=[
            {"role": "user", "content": prompt}
        ],
        system="You are an expert ATS (Applicant Tracking System) analyst and career coach who helps candidates optimize their resumes for specific jobs."
    )

    content = response.content[0].text

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


def get_resume_improvements(resume_text: str, target_job_description: str = None) -> str:
    """Get specific suggestions to improve a resume."""
    anthropic_client = get_client()

    job_context = ""
    if target_job_description:
        job_context = f"""
Target Job Description:
{target_job_description}

Tailor your suggestions to help this resume better match this specific job.
"""

    prompt = f"""Review this resume and provide specific improvement suggestions.

Resume:
{resume_text}
{job_context}

Provide actionable suggestions in these categories:

1. CONTENT IMPROVEMENTS
- Specific changes to bullet points, descriptions, or sections
- Missing information that should be added

2. ACTION VERBS
- Weak verbs to replace and stronger alternatives
- Examples of how to rewrite specific bullets

3. QUANTIFIABLE ACHIEVEMENTS
- Identify bullets that could include numbers/metrics
- Suggest how to quantify vague statements

4. FORMATTING RECOMMENDATIONS
- Structure and organization suggestions
- Readability improvements

5. KEYWORDS TO ADD
- Industry-specific terms that are missing
- Technical skills to highlight

Be specific and reference actual content from the resume when possible.
"""

    response = _create_message(anthropic_client, 
        model=get_claude_model(),
        max_tokens=1500,
        messages=[
            {"role": "user", "content": prompt}
        ],
        system="You are a professional resume writer and career coach with expertise in creating impactful resumes that get interviews."
    )

    return response.content[0].text


def generate_company_research(company_name: str, industry: str = None, website: str = None) -> str:
    """Generate a company research summary for interview prep."""
    anthropic_client = get_client()

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

    response = _create_message(anthropic_client, 
        model=get_claude_model(),
        max_tokens=1500,
        messages=[
            {"role": "user", "content": prompt}
        ],
        system="You are a career coach helping candidates prepare for interviews by researching companies. Provide helpful, accurate information based on general knowledge about well-known companies, and general industry insights for less known companies."
    )

    return response.content[0].text


def summarize_job_description(job_title: str, job_description: str) -> dict:
    """
    Generate a comprehensive summary of a job description including role overview,
    responsibilities, qualifications, and compensation.

    Returns:
        dict with 'summary' (comprehensive job summary) and 'tech_tools' (list of technologies)
    """
    if not job_description or len(job_description.strip()) < 50:
        return {"summary": "", "tech_tools": []}

    anthropic_client = get_client()

    prompt = f"""Extract the key information from this job posting for a job seeker.

Job Title: {job_title}

Job Posting Text:
{job_description[:6000]}

CRITICAL: You must ONLY describe what THIS SPECIFIC JOB ROLE involves.
DO NOT describe the company, its mission, its values, or what the company does.
ONLY extract information about the actual job duties and requirements.

Format your response EXACTLY like this:

**Summary**
[2-3 sentences describing what this job role does day-to-day. Focus ONLY on the employee's work, NOT the company.]

**Responsibilities**
• [duty 1]
• [duty 2]
• [duty 3]
• [duty 4]
• [duty 5]
[List 4-6 main job duties extracted from the posting]

**Minimum Qualifications**
• [required qualification 1]
• [required qualification 2]
• [required qualification 3]
[List the REQUIRED qualifications - years of experience, degrees, must-have skills]

**Preferred Qualifications**
• [nice-to-have 1]
• [nice-to-have 2]
[List bonus qualifications. Write "None specified" if not mentioned]

**Pay & Benefits**
[Salary range, bonus, equity, benefits like PTO, health insurance, remote work. Write "Not specified" if not mentioned]

**Technologies**
[Comma-separated list of tools, languages, frameworks, platforms mentioned]

RULES:
1. NEVER mention the company name or describe what the company does
2. NEVER include company mission, values, or culture statements
3. ONLY describe the job responsibilities and requirements
4. Extract exact requirements from the posting - do not make things up
5. Keep bullet points short (under 12 words each)
"""

    try:
        response = _create_message(anthropic_client, 
            model=get_claude_model(),
            max_tokens=800,
            messages=[
                {"role": "user", "content": prompt}
            ],
            system="You are an expert job analyst who creates clear, accurate summaries of job postings. Focus on extracting the most important information that helps candidates evaluate fit."
        )

        content = response.content[0].text.strip()

        # Extract tech stack from the response for the separate field
        tech_tools = []
        if "**Technologies**" in content:
            tech_section = content.split("**Technologies**")[1].strip()
            # Get just the first line/paragraph after the header
            tech_line = tech_section.split("\n")[0].strip()
            if tech_line and tech_line.lower() not in ["not specified", "none specified", "none"]:
                # Split by comma and clean up
                tech_tools = [t.strip() for t in tech_line.split(",") if t.strip()][:10]

        return {
            "summary": content,
            "tech_tools": tech_tools
        }
    except Exception as e:
        print(f"Error summarizing job: {e}")
        return {"summary": "", "tech_tools": []}


def generate_ats_tailored_resume(resume_text: str, job_title: str, job_description: str, company_name: str = None) -> str:
    """Generate an ATS-optimized resume tailored to a specific job."""
    anthropic_client = get_client()

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

    response = _create_message(anthropic_client, 
        model=get_claude_model(),
        max_tokens=3000,
        messages=[
            {"role": "user", "content": prompt}
        ],
        system="You are a professional resume writer specializing in ATS optimization. You transform resumes to maximize their chances of passing ATS screening and impressing recruiters for specific job postings."
    )

    return response.content[0].text


def complete_text(system: str, prompt: str, max_tokens: int = 1000) -> str:
    """Single-turn completion with the configured Claude model."""
    anthropic_client = get_client()
    message = _create_message(
        anthropic_client,
        model=get_claude_model(),
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(getattr(block, "text", "") for block in message.content)
