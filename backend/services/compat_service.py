"""
Gemini, Groq, DeepSeek and Qwen: the same prompts as openai_service, run on
the provider's OpenAI-compatible endpoint with its key and chosen model
(services/providers.py). get_service() in ai_service.py returns one of these.
"""
import os

from openai import OpenAI

from services import openai_service
from services.providers import PROVIDERS, default_model

# Room for reasoning on models that think before answering (Gemini 3,
# DeepSeek, Qwen 3); unused tokens are not billed.
THINKING_HEADROOM = {"gemini": 2048, "deepseek": 2048, "qwen": 2048}

# The public functions every AI service offers (ai_service.py routes to them).
FUNCTIONS = (
    "generate_cover_letter",
    "generate_interview_questions",
    "analyze_resume_job_match",
    "generate_company_research",
    "generate_ats_tailored_resume",
    "complete_text",
)

_clients = {}


def api_key(provider: str):
    """The provider's key: its environment variable first, else the saved setting."""
    p = PROVIDERS[provider]
    for var in p["env"]:
        if os.environ.get(var):
            return os.environ[var]
    return openai_service.get_db_setting(p["key_setting"])


def model(provider: str) -> str:
    """The admin's chosen model for the provider, else its default."""
    chosen = openai_service.get_db_setting(PROVIDERS[provider]["model_setting"])
    return chosen if chosen in PROVIDERS[provider]["models"] else default_model(provider)


def client(provider: str) -> OpenAI:
    key = api_key(provider)
    if not key:
        raise ValueError(f"{PROVIDERS[provider]['name']} API key not configured. Set it in Settings › AI Config.")
    cached = _clients.get(provider)
    if cached is None or cached[0] != key:
        cached = (key, OpenAI(api_key=key, base_url=PROVIDERS[provider]["base_url"]))
        _clients[provider] = cached
    return cached[1]


class CompatService:
    """openai_service's functions bound to one OpenAI-compatible provider."""

    def __init__(self, provider: str):
        if provider not in PROVIDERS or "base_url" not in PROVIDERS[provider]:
            raise ValueError(f"Not an OpenAI-compatible provider: {provider}")
        self.provider = provider

    def __getattr__(self, name):
        if name not in FUNCTIONS:
            raise AttributeError(name)
        fn = getattr(openai_service, name)

        def bound(*args, **kwargs):
            token = openai_service._bound.set({
                "client": client(self.provider),
                "model": model(self.provider),
                "headroom": THINKING_HEADROOM.get(self.provider, 0),
            })
            try:
                return fn(*args, **kwargs)
            finally:
                openai_service._bound.reset(token)

        return bound
