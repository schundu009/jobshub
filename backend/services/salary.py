"""
A full-time job's pay, read from its description when the scraper gave none.

Uses the contract feed's pay parser (contracts.classifier.parse_pay), which
already handles ranges, "k" amounts, periods and the bonus/funding traps.
jobs.salary_min/max stay yearly, so the board's salary filter and sort compare
like with like: a yearly range is stored as is; an hourly one ("$27-34/hr")
keeps its rate in hourly_rate_min/max and its yearly equivalent (x 2080 hours)
in salary_min/max. Other periods (day, week, month) are not stored.
"""
from typing import Optional

from contracts.classifier import parse_pay, to_text

HOURS_PER_YEAR = 2080
_EMPTY = {"salary_min": None, "salary_max": None, "hourly_rate_min": None, "hourly_rate_max": None}


def pay_from_text(description: Optional[str]) -> dict:
    """The jobs pay columns for the pay ``description`` states (all None when none)."""
    parsed = parse_pay(to_text(description))
    if not parsed or parsed[2] not in ("year", "hour"):
        return dict(_EMPTY)
    lo, hi, period = parsed
    if period == "year":
        return {**_EMPTY, "salary_min": int(round(lo)), "salary_max": int(round(hi)) if hi is not None else None}
    return {
        "salary_min": int(round(lo * HOURS_PER_YEAR)),
        "salary_max": int(round(hi * HOURS_PER_YEAR)) if hi is not None else None,
        "hourly_rate_min": round(lo, 2),
        "hourly_rate_max": round(hi, 2) if hi is not None else None,
    }


def fill_salary(job, description: Optional[str] = None) -> bool:
    """Set ``job``'s pay columns from its description when it has no salary."""
    if job.salary_min or job.salary_max:
        return False
    pay = pay_from_text(description if description is not None else job.job_description)
    if pay["salary_min"] is None:
        return False
    for k, v in pay.items():
        setattr(job, k, v)
    return True
