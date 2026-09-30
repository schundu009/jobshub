"""
AI Service Router - Routes AI requests to the appropriate provider (OpenAI or Anthropic).
"""
from typing import Optional


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


def get_default_provider() -> str:
    """Get the default AI provider from database."""
    return get_db_setting("default_ai_provider", "openai")


def get_service():
    """Get the appropriate AI service based on the default provider setting."""
    provider = get_default_provider()

    if provider == "anthropic":
        from services import anthropic_service
        return anthropic_service
    else:
        from services import openai_service
        return openai_service


def generate_cover_letter(job_title: str, company_name: str, job_description: str, resume_text: str) -> str:
    """Generate a tailored cover letter for a specific job."""
    service = get_service()
    return service.generate_cover_letter(job_title, company_name, job_description, resume_text)


def generate_interview_questions(job_title: str, job_description: str, interview_type: str) -> str:
    """Generate practice interview questions based on the job."""
    service = get_service()
    return service.generate_interview_questions(job_title, job_description, interview_type)


def analyze_resume_job_match(job_description: str, resume_text: str) -> dict:
    """Analyze how well a resume matches a job posting."""
    service = get_service()
    return service.analyze_resume_job_match(job_description, resume_text)


def get_resume_improvements(resume_text: str, target_job_description: str = None) -> str:
    """Get specific suggestions to improve a resume."""
    service = get_service()
    return service.get_resume_improvements(resume_text, target_job_description)


def generate_company_research(company_name: str, industry: str = None, website: str = None) -> str:
    """Generate a company research summary for interview prep."""
    service = get_service()
    return service.generate_company_research(company_name, industry, website)


def summarize_job_description(job_title: str, job_description: str) -> dict:
    """Generate a comprehensive summary of a job description."""
    service = get_service()
    return service.summarize_job_description(job_title, job_description)


def generate_ats_tailored_resume(resume_text: str, job_title: str, job_description: str, company_name: str = None) -> str:
    """Generate an ATS-optimized resume tailored to a specific job."""
    service = get_service()
    return service.generate_ats_tailored_resume(resume_text, job_title, job_description, company_name)


def complete_text(system: str, prompt: str, max_tokens: int = 1000) -> str:
    """Single-turn completion on the default provider (used by Auto Apply answer drafting)."""
    service = get_service()
    return service.complete_text(system, prompt, max_tokens)
