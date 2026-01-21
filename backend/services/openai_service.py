import os
from openai import OpenAI

client = None


def get_client():
    global client
    if client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        client = OpenAI(api_key=api_key)
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
        model="gpt-4o-mini",
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
        model="gpt-4o-mini",
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
        model="gpt-4o-mini",
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


def get_resume_improvements(resume_text: str, target_job_description: str = None) -> str:
    """Get specific suggestions to improve a resume."""
    openai_client = get_client()

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

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a professional resume writer and career coach with expertise in creating impactful resumes that get interviews."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.5,
        max_tokens=1500
    )

    return response.choices[0].message.content


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
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a career coach helping candidates prepare for interviews by researching companies. Provide helpful, accurate information based on general knowledge about well-known companies, and general industry insights for less known companies."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=1500
    )

    return response.choices[0].message.content


def summarize_job_description(job_title: str, job_description: str) -> dict:
    """
    Generate a high-level summary of a job description including key responsibilities
    and technology/tools required.

    Returns:
        dict with 'summary' (brief role description) and 'tech_tools' (list of technologies)
    """
    if not job_description or len(job_description.strip()) < 50:
        return {"summary": "", "tech_tools": []}

    openai_client = get_client()

    prompt = f"""Analyze this job posting and provide a concise summary.

Job Title: {job_title}

Job Description:
{job_description[:4000]}

Respond in this exact JSON format:
{{
    "summary": "A 1-2 sentence high-level description of the role and main responsibilities",
    "tech_tools": ["tool1", "tool2", "tool3"]
}}

Rules:
- summary: Focus on the core role purpose and key responsibilities (max 150 chars)
- tech_tools: List 3-8 key technologies, tools, frameworks, or languages mentioned (use short names like "Python", "AWS", "React", "SQL")
- Keep tech_tools concise - single words or short phrases only
- Only include tools/tech explicitly mentioned or strongly implied
- Return valid JSON only, no markdown or explanation
"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a technical recruiter who summarizes job descriptions. Always respond with valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=300
        )

        content = response.choices[0].message.content.strip()
        # Clean up potential markdown code blocks
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        import json
        result = json.loads(content)
        return {
            "summary": result.get("summary", "")[:200],
            "tech_tools": result.get("tech_tools", [])[:10]
        }
    except Exception as e:
        print(f"Error summarizing job: {e}")
        return {"summary": "", "tech_tools": []}


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
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a professional resume writer specializing in ATS optimization. You transform resumes to maximize their chances of passing ATS screening and impressing recruiters for specific job postings."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.5,
        max_tokens=3000
    )

    return response.choices[0].message.content
