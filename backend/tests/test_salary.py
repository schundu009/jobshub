from types import SimpleNamespace

import pytest

from services.salary import fill_salary, yearly_salary


@pytest.mark.parametrize("text, expected", [
    ("<p>The base pay range for this role is $196,000 - $227,000 USD.</p>", (196000, 227000)),
    ("Salary range $120k–$150k", (120000, 150000)),
    ("Compensation: $95,000 - $110,000", (95000, 110000)),
    ("&lt;p&gt;Salary: $140,000 to $200,000 per year&lt;/p&gt;", (140000, 200000)),
    ("Pay: $65/hr on W2", (None, None)),          # hourly is not a yearly salary
    ("We raised $50 million in Series B funding.", (None, None)),
    ("$5,000 sign-on bonus!", (None, None)),
    ("", (None, None)),
    (None, (None, None)),
])
def test_yearly_salary(text, expected):
    assert yearly_salary(text) == expected


def test_fill_salary_only_when_empty():
    job = SimpleNamespace(salary_min=None, salary_max=None, job_description="Salary range $120k-$150k")
    assert fill_salary(job) is True
    assert (job.salary_min, job.salary_max) == (120000, 150000)
    kept = SimpleNamespace(salary_min=90000, salary_max=None, job_description="Salary range $120k-$150k")
    assert fill_salary(kept) is False
    assert kept.salary_min == 90000
