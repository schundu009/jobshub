"""
AI providers (services/providers.py): every provider in Settings › AI Config,
keys and models per provider, the default provider, and OpenAI-compatible
providers (Gemini, Groq, DeepSeek, Qwen) running openai_service's prompts on
their own endpoint, key and model.
"""
from types import SimpleNamespace

import pytest

from models import AppSetting
from tests.test_admin_and_scraping_fixes import headers, make_user


@pytest.fixture
def admin(db):
    return make_user(db, "admin@example.com", role="admin")


@pytest.fixture(autouse=True)
def _no_env_keys(monkeypatch):
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_AI_API_KEY",
                "GROQ_API_KEY", "DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def test_ai_model_lists_every_provider(client, admin):
    body = client.get("/api/settings/ai-model", headers=headers(admin)).json()
    ids = [p["id"] for p in body["providers"]]
    assert ids == ["openai", "anthropic", "gemini", "groq", "deepseek", "qwen"]
    by = {p["id"]: p for p in body["providers"]}
    assert by["gemini"]["model"] == "gemini-3.8-flash"
    assert by["groq"]["models"][0]["id"] == "openai/gpt-oss-120b"
    assert by["deepseek"]["key"]["is_set"] is False
    assert body["default_provider"] == "openai"
    # The fields older pages read are still there.
    assert body["claude_model"] and body["openai_models"]


def test_model_choice_is_stored_per_provider(client, db, admin):
    for model, key in [("gemini-3.1-pro-preview", "gemini_model"), ("llama-3.3-70b-versatile", "groq_model"),
                       ("deepseek-v4-pro", "deepseek_model"), ("qwen3.8-max", "qwen_model"),
                       ("claude-fable-5-1", "claude_model"), ("gpt-6.1-sol", "ai_model")]:
        r = client.post("/api/settings/ai-model", json={"model": model}, headers=headers(admin))
        assert r.status_code == 200, r.text
        assert db.query(AppSetting).filter_by(key=key).one().value == model
    by = {p["id"]: p for p in client.get("/api/settings/ai-model", headers=headers(admin)).json()["providers"]}
    assert by["qwen"]["model"] == "qwen3.8-max"
    assert client.post("/api/settings/ai-model", json={"model": "nope-1"}, headers=headers(admin)).status_code == 400


def test_keys_per_provider(client, db, admin):
    bad = client.post("/api/settings/api-key", json={"provider": "groq", "api_key": "sk-abcdefghijklmnopqrstuv"},
                      headers=headers(admin))
    assert bad.status_code == 400 and "gsk_" in bad.json()["detail"]
    ok = client.post("/api/settings/api-key", json={"provider": "groq", "api_key": "gsk_abcdefghijklmnopqrstuv"},
                     headers=headers(admin))
    assert ok.status_code == 200
    assert db.query(AppSetting).filter_by(key="groq_api_key").one().value == "gsk_abcdefghijklmnopqrstuv"
    status = client.get("/api/settings/api-key?provider=groq", headers=headers(admin)).json()
    assert status == {"is_set": True, "key_preview": "gsk_****...****", "source": "database", "provider": "groq"}
    assert client.delete("/api/settings/api-key?provider=groq", headers=headers(admin)).status_code == 200
    assert client.get("/api/settings/api-key?provider=groq", headers=headers(admin)).json()["is_set"] is False
    assert client.get("/api/settings/api-key?provider=mars", headers=headers(admin)).status_code == 400


def test_env_key_wins_for_gemini(client, admin, monkeypatch):
    monkeypatch.setenv("GOOGLE_AI_API_KEY", "AIzaSyTestTestTestTestTest")
    status = client.get("/api/settings/api-key?provider=gemini", headers=headers(admin)).json()
    assert status["is_set"] is True and status["source"] == "environment"


def test_default_provider_accepts_every_provider(client, admin, monkeypatch):
    from services import ai_service
    assert client.post("/api/settings/default-ai-provider", json={"provider": "deepseek"},
                       headers=headers(admin)).status_code == 200
    assert client.get("/api/settings/default-ai-provider", headers=headers(admin)).json() == {"provider": "deepseek"}
    assert client.post("/api/settings/default-ai-provider", json={"provider": "mars"},
                       headers=headers(admin)).status_code == 400
    monkeypatch.setattr(ai_service, "get_db_setting", lambda key, default=None: "qwen")
    svc = ai_service.get_service()
    assert svc.provider == "qwen"


def test_compat_provider_runs_openai_prompts_on_its_own_client(monkeypatch):
    from services import compat_service, openai_service

    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="from groq"))])

    fake = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    monkeypatch.setattr(compat_service, "client", lambda provider: fake)
    settings = {"groq_model": "llama-3.1-8b-instant"}
    monkeypatch.setattr(openai_service, "get_db_setting", lambda key, default=None: settings.get(key, default))

    out = compat_service.CompatService("groq").complete_text("sys", "hi", max_tokens=100, feature="auto_apply_draft")
    assert out == "from groq"
    # The provider's chosen model, not OpenAI's per-feature map; classic params for non-GPT-5/6 models.
    assert calls[0]["model"] == "llama-3.1-8b-instant"
    assert calls[0]["max_tokens"] == 100 and calls[0]["temperature"] == 0.3
    # Outside the call, openai_service is back on OpenAI.
    assert openai_service._bound.get() is None
    assert openai_service.get_ai_model("auto_apply_draft") == "gpt-5.6-luna"


def test_compat_thinking_headroom_and_missing_key(monkeypatch):
    from services import compat_service, openai_service

    calls = []
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kw: calls.append(kw) or SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]))))
    monkeypatch.setattr(compat_service, "client", lambda provider: fake)
    monkeypatch.setattr(openai_service, "get_db_setting", lambda key, default=None: default)
    compat_service.CompatService("gemini").complete_text("s", "p", max_tokens=500)
    assert calls[0]["model"] == "gemini-3.8-flash" and calls[0]["max_tokens"] == 500 + 2048

    monkeypatch.undo()
    monkeypatch.setattr(openai_service, "get_db_setting", lambda key, default=None: None)
    with pytest.raises(ValueError, match="DeepSeek API key not configured"):
        compat_service.client("deepseek")


def test_claude_reads_text_after_thinking_blocks():
    from services.anthropic_service import _create_message, _text

    resp = SimpleNamespace(content=[SimpleNamespace(type="thinking", thinking="..."),
                                    SimpleNamespace(type="text", text="Hello "), SimpleNamespace(type="text", text="there")])
    assert _text(resp) == "Hello there"
    seen = {}
    fake = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: seen.update(kw) or resp))
    _create_message(fake, model="claude-fable-5-1", max_tokens=1000, messages=[])
    assert seen["max_tokens"] == 1000 + 4096
    _create_message(fake, model="claude-haiku-4-5-20251001", max_tokens=1000, messages=[])
    assert seen["max_tokens"] == 1000
