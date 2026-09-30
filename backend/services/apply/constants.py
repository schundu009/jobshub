"""Shared constants for Cariara Auto Apply."""
import os

SUPPORTED_ATS = ("greenhouse", "lever", "ashby")

MODES = ("review", "auto")

# Status machine. Every transition writes an ApplicationEvent.
STATUSES = (
    "suggested", "drafting", "needs_input", "ready_for_review", "approved",
    "handed_off", "submitted", "confirmed",
    "skipped", "failed", "unsupported", "withdrawn",
)

ALLOWED_TRANSITIONS = {
    "suggested": {"drafting", "skipped"},
    "drafting": {"needs_input", "ready_for_review", "approved", "unsupported", "failed", "skipped"},
    "needs_input": {"ready_for_review", "needs_input", "approved", "drafting", "skipped", "submitted", "withdrawn"},
    "ready_for_review": {"needs_input", "ready_for_review", "approved", "drafting", "skipped", "submitted", "withdrawn"},
    "approved": {"handed_off", "needs_input", "ready_for_review", "drafting", "skipped", "submitted", "failed", "withdrawn"},
    "handed_off": {"submitted", "failed", "approved", "needs_input", "ready_for_review", "skipped", "withdrawn"},
    "submitted": {"confirmed", "withdrawn"},
    "confirmed": {"withdrawn"},
    "skipped": {"drafting"},
    "failed": {"drafting", "skipped", "submitted"},
    "unsupported": {"drafting", "skipped", "submitted"},
    "withdrawn": set(),
}

EDITABLE_STATUSES = {"needs_input", "ready_for_review", "approved", "handed_off"}

QUESTION_TYPES = ("text", "textarea", "select", "multiselect", "boolean", "file", "date", "number")

CATEGORIES = (
    "identity", "links", "resume", "cover_letter", "work_auth", "sponsorship",
    "relocation", "salary", "start_date", "eeo", "attestation", "custom",
)

ANSWER_SOURCES = ("profile", "bank", "ai_draft", "user")

# Daily caps. Paid plans may pick any cap up to APPLY_DAILY_CAP_MAX.
DEFAULT_DAILY_CAP = int(os.getenv("APPLY_DEFAULT_DAILY_CAP", "10"))
PAID_DAILY_CAP_MAX = int(os.getenv("APPLY_DAILY_CAP_MAX", "25"))

DEFAULT_MIN_MATCH_SCORE = 70

# Matching
MATCH_LOOKBACK_DAYS = 14
QUEUE_SIZE = 100
MATCH_MIN_SCORE_TO_STORE = 20

# Form schema cache
SCHEMA_TTL_HOURS = 24

PLAN_REQUIRED_DETAIL = "Auto Apply is available on paid plans"
