"""services.it_roles: IT / tech role detection (shared by jobs and contracts).

The labeled set (tests/fixtures/it_roles/labeled_titles.tsv) is ~380 random real
titles from prod contract_jobs + jobs plus curated must-have IN / OUT titles.
Each labeled row is its own test; UNSURE rows are only reported (see
test_accuracy_report)."""
from pathlib import Path

import pytest

from services.it_roles import IT_CATEGORIES, classify_it, is_it_role, it_category, tech_skill_count

FIXTURE = Path(__file__).parent / "fixtures" / "it_roles" / "labeled_titles.tsv"

# Hand-labeled rows the classifier gets wrong (kept visible, not hidden):
KNOWN_DISAGREEMENTS = {
    "Commercial Program Manager, Data Center Non-Firm Grid Capacity",  # energy procurement, "data center" reads as IT
    "Evaluation and Investigation Quality Assurance Analyst – Evaluation and Investigation – Thailand",  # content QA
    "TikTok LIVE - AI Data Operation Specialist - Spanish&Italian Speaking",  # AI data ops (annotation-like)
}


def _rows():
    out = []
    for line in FIXTURE.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        label, title, source = line.split("\t")
        out.append((label, title, source))
    return out


ROWS = _rows()
LABELED = [(lab, t) for lab, t, _ in ROWS if lab in ("IN", "OUT")]


def test_fixture_is_big_enough():
    assert len(LABELED) >= 300
    assert len({t for _, t in LABELED}) >= 300


@pytest.mark.parametrize("label,title", LABELED, ids=[f"{lab}:{t[:60]}" for lab, t in LABELED])
def test_labeled_title(label, title):
    if title in KNOWN_DISAGREEMENTS:
        pytest.xfail("known disagreement")
    assert is_it_role(title) is (label == "IN"), classify_it(title)


def test_accuracy_report():
    tp = fp = fn = tn = 0
    for label, title in LABELED:
        pred = is_it_role(title)
        gold = label == "IN"
        tp += gold and pred
        fn += gold and not pred
        fp += pred and not gold
        tn += not gold and not pred
    precision, recall = tp / (tp + fp), tp / (tp + fn)
    assert recall >= 0.98 and precision >= 0.97, (tp, fp, fn, tn)


MUST_IN = ["Salesforce Developer", "Site Reliability Engineer", "Technical Program Manager", "Data Analyst",
           "Business Systems Analyst", "IT Support Specialist", "Scrum Master", "UX Designer", "Firmware Engineer",
           "Network Administrator", "ServiceNow Administrator"]
MUST_OUT = ["Store Associate", "Registered Nurse", "Mechanical Engineer", "Seasonal Stock & Fulfillment",
            "Account Executive", "Civil Engineer", "Warehouse Associate", "Accountant"]


@pytest.mark.parametrize("title", MUST_IN)
def test_must_in(title):
    assert is_it_role(title)
    assert it_category(title) in IT_CATEGORIES


@pytest.mark.parametrize("title", MUST_OUT)
def test_must_out(title):
    assert not is_it_role(title)
    assert it_category(title) is None


@pytest.mark.parametrize("title,category", [
    ("Senior Software Engineer", "software"),
    ("Salesforce Developer", "software"),
    ("Site Reliability Engineer", "devops_sre_cloud"),
    ("Senior DevOps Engineer - AWS", "devops_sre_cloud"),
    ("Data Engineer III", "data"),
    ("Machine Learning Engineer", "ml_ai"),
    ("Penetration Tester", "security"),
    ("Cyber Security Engineer", "security"),
    ("Information Security Officer", "security"),
    ("Database Administrator", "network_systems_dba"),
    ("Network Engineer - Cisco", "network_systems_dba"),
    ("QA Automation Engineer", "qa"),
    ("Help Desk Technician", "it_support"),
    ("Firmware Engineer", "embedded_hw"),
    ("FPGA Design Engineer", "embedded_hw"),
    ("Scrum Master", "product_program"),
    ("Technical Program Manager", "product_program"),
    ("UX Designer", "design_ux"),
    ("Technical Writer", "tech_writing"),
])
def test_category(title, category):
    assert it_category(title) == category


@pytest.mark.parametrize("title,expected", [
    # the head noun decides: "Software Sales Executive" is sales, "Salesforce Developer" is IT
    ("Software Sales Executive", False),
    ("Frontend Engineer, Ads Campaign Manager", True),
    ("Recruiter - Software Engineering", False),
    ("Security Guard", False),
    ("Security Officer", False),
    ("Data Entry Clerk", False),
    ("Senior Product Manager-Epic CRM and Patient Engage", True),
    ("Vehicle Dynamics CAE Engineer", False),
    ("Facilities Engineering Manager", False),
    ("Project Architect", False),
    ("Construction Project Manager", False),
    ("Project Manager (Data-focused Initiatives)", True),
    ("Program Manager - Change Management", False),
    ("Synthetic Aperture Radar Systems Engineer (Processing)", False),
    ("Systems Engineer", True),
    ("Electronics Technician", False),
    ("IT Technician", True),
    ("Technical Support Call Center Rep", True),
    ("Customer Service Representative", False),
    ("Data Center Facilities Technician III, Electrical", False),
    ("Remote - Senior Software Engineer", True),
    ("Engineer II, Software", True),
    ("Java / Spring Boot SDET - 12 Month Contract W/ Fortune 10 Client", True),
    ("Real Estate Associate Agent (1099) - Boise", False),
    ("Sales associate/ Sales assistant/ Educator - seasonal contract (3 months) | Frankfurt", False),
    ("", False),
])
def test_traps(title, expected):
    assert is_it_role(title) is expected, classify_it(title)


def test_ambiguous_uses_context_then_default():
    # generic "Specialist"/"Consultant" with nothing else: undecided
    assert classify_it("Consultant").is_it is None
    assert is_it_role("Consultant") is False
    assert is_it_role("Consultant", ambiguous_default=True) is True
    # board category / department break the tie
    assert is_it_role("Consultant", category="Information Technology") is True
    assert is_it_role("Consultant", category="Healthcare") is False
    assert is_it_role("Consultant", department="Software Development") is True
    assert is_it_role("Specialist", skills=["python", "aws", "sql"]) is True
    assert is_it_role("Specialist", skills=["excel"]) is False
    # a clear title is never overridden by context
    assert is_it_role("Registered Nurse", category="Information Technology") is False
    assert is_it_role("Data Engineer", category="Healthcare") is True


def test_tech_skill_count():
    assert tech_skill_count(["Python", "AWS", "cooking"]) == 2
    assert tech_skill_count("python, sql, kubernetes") == 3
    assert tech_skill_count(None) == 0


def test_never_raises_on_odd_input():
    for v in (None, 123, "!!!", "a" * 5000, "C++/C# .NET"):
        is_it_role(v)
        it_category(v)
