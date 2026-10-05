"""
AI Service Router - Routes AI requests to the appropriate provider (OpenAI or Anthropic).
"""


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


DEFAULT_PROVIDER = "openai"


def get_default_provider() -> str:
    """The admin's default_ai_provider setting; OpenAI when unset or unrecognized."""
    provider = get_db_setting("default_ai_provider", DEFAULT_PROVIDER)
    return provider if provider in ("openai", "anthropic") else DEFAULT_PROVIDER


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


def generate_company_research(company_name: str, industry: str = None, website: str = None) -> str:
    """Generate a company research summary for interview prep."""
    service = get_service()
    return service.generate_company_research(company_name, industry, website)


def generate_ats_tailored_resume(resume_text: str, job_title: str, job_description: str, company_name: str = None) -> str:
    """Generate an ATS-optimized resume tailored to a specific job."""
    service = get_service()
    return service.generate_ats_tailored_resume(resume_text, job_title, job_description, company_name)


def complete_text(system: str, prompt: str, max_tokens: int = 1000, feature: str = None) -> str:
    """Single-turn completion on the default provider.

    `feature` picks a per-feature model where the provider has one
    (openai_service.FEATURE_MODELS, e.g. "auto_apply_draft" -> gpt-5.6-luna).
    """
    service = get_service()
    return service.complete_text(system, prompt, max_tokens, feature=feature)
