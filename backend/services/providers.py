"""
The AI providers the admin can pick (Settings › AI Config).

OpenAI and Anthropic have their own services. The rest speak the OpenAI chat
API at their own base URL, so they run through openai_service's prompts with
their own client and model (compat_service.py).

Each provider: display name, models {id: "Name (blurb)"} with the default
first, the env vars that override a saved key, the AppSetting keys for the
key and the chosen model, and the prefix a key must start with.
"""

PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "env": ("OPENAI_API_KEY",),
        "key_setting": "openai_api_key",
        "model_setting": "ai_model",
        "key_prefix": "sk-",
    },
    "anthropic": {
        "name": "Anthropic",
        "env": ("ANTHROPIC_API_KEY",),
        "key_setting": "anthropic_api_key",
        "model_setting": "claude_model",
        "key_prefix": "sk-ant-",
    },
    "gemini": {
        "name": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "env": ("GEMINI_API_KEY", "GOOGLE_AI_API_KEY"),
        "key_setting": "gemini_api_key",
        "model_setting": "gemini_model",
        "key_prefix": "AIza",
        "models": {
            "gemini-3.8-flash": "Gemini 3.8 Flash (Default, fast)",
            "gemini-3.5-flash-lite": "Gemini 3.5 Flash-Lite (Cheapest)",
            "gemini-3.1-pro-preview": "Gemini 3.1 Pro (Most capable, preview)",
        },
    },
    "groq": {
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "env": ("GROQ_API_KEY",),
        "key_setting": "groq_api_key",
        "model_setting": "groq_model",
        "key_prefix": "gsk_",
        "models": {
            "openai/gpt-oss-120b": "GPT-OSS 120B (Default, fast)",
            "openai/gpt-oss-20b": "GPT-OSS 20B (Cheapest, fastest)",
            "llama-3.3-70b-versatile": "Llama 3.3 70B (Versatile)",
            "llama-3.1-8b-instant": "Llama 3.1 8B (Instant)",
        },
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "env": ("DEEPSEEK_API_KEY",),
        "key_setting": "deepseek_api_key",
        "model_setting": "deepseek_model",
        "key_prefix": "sk-",
        "models": {
            "deepseek-flash": "DeepSeek V4.1 Flash (Default, cheapest)",
            "deepseek-v4-pro": "DeepSeek V4 Pro (Most capable)",
        },
    },
    "qwen": {
        "name": "Qwen (Alibaba Cloud)",
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "env": ("DASHSCOPE_API_KEY",),
        "key_setting": "qwen_api_key",
        "model_setting": "qwen_model",
        "key_prefix": "sk-",
        "models": {
            "qwen3.7-plus": "Qwen 3.7 Plus (Default, balanced)",
            "qwen3.8-flash": "Qwen 3.8 Flash (Cheapest, fast)",
            "qwen3.8-max": "Qwen 3.8 Max (Most capable)",
        },
    },
}

PROVIDER_IDS = tuple(PROVIDERS)
COMPAT_PROVIDER_IDS = tuple(p for p, v in PROVIDERS.items() if "base_url" in v)


def models_for(provider: str) -> dict:
    """{model id: label} for a provider; OpenAI's and Anthropic's live in their services."""
    if provider == "openai":
        from services.openai_service import OPENAI_MODELS
        return OPENAI_MODELS
    if provider == "anthropic":
        from services.anthropic_service import CLAUDE_MODELS
        return CLAUDE_MODELS
    return PROVIDERS[provider]["models"]


def default_model(provider: str) -> str:
    if provider == "openai":
        from services.openai_service import DEFAULT_MODEL
        return DEFAULT_MODEL
    if provider == "anthropic":
        from services.anthropic_service import DEFAULT_MODEL
        return DEFAULT_MODEL
    return next(iter(PROVIDERS[provider]["models"]))


def provider_of_model(model: str):
    """The provider offering a model id, or None."""
    for pid in PROVIDER_IDS:
        if model in models_for(pid):
            return pid
    return None
