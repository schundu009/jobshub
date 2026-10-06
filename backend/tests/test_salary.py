from types import SimpleNamespace

import pytest

from services.salary import fill_salary, pay_from_text

_NONE = (None, None, None, None)


def _cols(pay):
    return pay["salary_min"], pay["salary_max"], pay["hourly_rate_min"], pay["hourly_rate_max"]


@pytest.mark.parametrize("text, expected", [
    ("<p>The base pay range for this role is $196,000 - $227,000 USD.</p>", (196000, 227000, None, None)),
    ("Salary range $120k–$150k", (120000, 150000, None, None)),
    ("Compensation: $95,000 - $110,000", (95000, 110000, None, None)),
    ("&lt;p&gt;Salary: $140,000 to $200,000 per year&lt;/p&gt;", (140000, 200000, None, None)),
    # hourly: the rate, and its yearly equivalent for the salary filter and sort
    ("Base Salary: $27-34/hr", (56160, 70720, 27.0, 34.0)),
    ("Pay: $65/hr on W2", (135200, None, 65.0, None)),
    ("$2,000 - $2,500 per week", _NONE),          # other periods are not stored
    ("We raised $50 million in Series B funding.", _NONE),
    ("$5,000 sign-on bonus!", _NONE),
    ("", _NONE),
    (None, _NONE),
])
def test_pay_from_text(text, expected):
    assert _cols(pay_from_text(text)) == expected


def _job(**kw):
    base = dict(salary_min=None, salary_max=None, hourly_rate_min=None, hourly_rate_max=None, job_description="")
    return SimpleNamespace(**{**base, **kw})


def test_fill_salary_only_when_empty():
    job = _job(job_description="Salary range $120k-$150k")
    assert fill_salary(job) is True
    assert (job.salary_min, job.salary_max, job.hourly_rate_min) == (120000, 150000, None)
    kept = _job(salary_min=90000, job_description="Salary range $120k-$150k")
    assert fill_salary(kept) is False
    assert kept.salary_min == 90000


def test_fill_salary_hourly():
    job = _job(job_description="Pay range $40 - $48 per hour")
    assert fill_salary(job) is True
    assert (job.hourly_rate_min, job.hourly_rate_max, job.salary_min) == (40.0, 48.0, 83200)
