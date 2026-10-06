"""
A full-time job's yearly salary, read from its description when the scraper
gave none.

Uses the contract feed's pay parser (contracts.classifier.parse_pay), which
already handles ranges, "k" amounts, periods and the bonus/funding traps. Only
a yearly figure is kept: jobs.salary_min/max are annual and the board shows
them as "$150K – $200K".
"""
from typing import Optional

from contracts.classifier import parse_pay, to_text


def yearly_salary(description: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    """(min, max) yearly pay stated in ``description``, or (None, None)."""
    parsed = parse_pay(to_text(description))
    if not parsed or parsed[2] != "year":
        return None, None
    lo, hi, _ = parsed
    return int(round(lo)), (int(round(hi)) if hi is not None else None)


def fill_salary(job, description: Optional[str] = None) -> bool:
    """Set ``job.salary_min/max`` from its description when both are empty."""
    if job.salary_min or job.salary_max:
        return False
    lo, hi = yearly_salary(description if description is not None else job.job_description)
    if lo is None:
        return False
    job.salary_min, job.salary_max = lo, hi
    return True
