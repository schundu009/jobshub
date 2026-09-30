"""contracts.classifier: realistic postings, including false-positive traps."""
import pytest

from contracts.classifier import (
    classify, contract_routing, detect_employment_type, employment_type_from_text, employment_type_from_title,
    is_us_location, map_employment_type_raw, parse_duration_months, parse_pay, tax_terms_from_text,
    visa_terms_from_text,
)

# ----------------------------------------------------------------- ATS labels

@pytest.mark.parametrize("raw, expected", [
    ("Contract", "contract"),
    ("Contractor", "contract"),
    ("Temporary", "temporary"),
    ("Temp", "temporary"),
    ("Contract to Hire", "contract_to_hire"),
    ("C2H", "contract_to_hire"),
    ("Contract-To-Hire", "contract_to_hire"),
    ("Freelance", "freelance"),
    ("Part-time", "part_time"),
    ("Full-time", "full_time"),
    ("FullTime", "full_time"),        # Ashby
    ("PartTime", "part_time"),
    ("Intern", "internship"),
    ("Full time - Contract", "contract"),
    ("Permanent", "full_time"),
    ("Regular", "full_time"),
    ("Seasonal", "temporary"),
    ("Fixed Term", "temporary"),
    ("Seasonal - Fixed Term", "temporary"),
    ("", None),
    ("Hybrid", None),
])
def test_ats_employment_labels(raw, expected):
    assert map_employment_type_raw(raw) == expected


# ------------------------------------------------------------------ titles

@pytest.mark.parametrize("title, expected", [
    ("Java Developer (Contract)", "contract"),
    ("Senior Data Engineer - Contract", "contract"),
    ("Contract Software Engineer", "contract"),
    ("Python Developer - Contract to Hire", "contract_to_hire"),
    ("QA Analyst (C2H)", "contract_to_hire"),
    ("Freelance Copywriter", "freelance"),
    ("Temporary Receptionist", "temporary"),
    ("Software Engineering Intern, Summer 2027", "internship"),
    ("Part-Time Bookkeeper", "part_time"),
    ("Independent Contractor - UX Designer", "contract"),
    # traps: the contract is the job's subject, not its terms
    ("Senior Contract Manager", None),
    ("Contracts Administrator", None),
    ("Government Contracts Specialist", None),
    ("Contract Negotiator", None),
    ("Contract Manufacturing Engineer", None),
    ("Contractor Safety Coordinator", None),
    ("Internal Audit Manager", None),
    ("International Tax Analyst", None),
    ("Template Designer", None),
    ("Engineer 1099", None),  # a number, not tax terms
    ("Site Reliability Engineer", None),
])
def test_titles(title, expected):
    assert employment_type_from_title(title) == expected


# -------------------------------------------------------------- descriptions

@pytest.mark.parametrize("text, expected", [
    ("This is a 6 month contract role with possible extension.", "contract"),
    ("12-month contract, W2 only, onsite 3 days a week.", "contract"),
    ("Contract-to-hire opportunity with a Fortune 500 client.", "contract_to_hire"),
    ("Duration: 6 months. Rate: $65/hr.", "contract"),
    ("Employment Type: Contract", "contract"),
    ("Long term contract with our banking client.", "contract"),
    ("This is a temporary assignment covering a leave.", "temporary"),
    ("This is a full-time, permanent position with benefits.", "full_time"),
    ("This is not a contract role; it is a full-time position.", "full_time"),
    # traps
    ("You will manage vendor contracts and lead contract negotiation.", None),
    ("As a federal contractor, we comply with all EEO requirements.", None),
    ("Experience with government contracts and contract management preferred.", None),
    ("Work closely with employees and contractors across the org.", None),
])
def test_description_types(text, expected):
    assert employment_type_from_text(text) == expected


def test_no_c2c_in_fte_posting_is_not_a_contract():
    assert detect_employment_type("Backend Engineer", "Full benefits. No C2C, no third parties.") is None


def test_ats_label_wins_over_text_but_title_marker_beats_fulltime_default():
    assert detect_employment_type("Data Engineer", "6 month contract", {"employment_type_raw": "FullTime"}) == "full_time"
    assert detect_employment_type("Data Engineer (Contract)", "", {"employment_type_raw": "Full-time"}) == "contract"
    assert detect_employment_type("Data Engineer", "contract to hire", {"employment_type_raw": "Contract"}) == "contract_to_hire"


# ----------------------------------------------------------------------- pay

@pytest.mark.parametrize("text, expected", [
    ("Pay: $65/hr on W2", (65.0, None, "hour")),
    ("$60-$75 per hour", (60.0, 75.0, "hour")),
    ("$60 - 75/hr", (60.0, 75.0, "hour")),
    ("Salary range $120k–$150k", (120000.0, 150000.0, "year")),
    ("USD 80.00/hour", (80.0, None, "hour")),
    ("$500/day outside IR35", (500.0, None, "day")),
    ("The base pay range is $120,000 - $150,000 per year.", (120000.0, 150000.0, "year")),
    ("Compensation: $95,000 - $110,000", (95000.0, 110000.0, "year")),
    ("Hourly rate: $55.50 - $62.25 an hour", (55.5, 62.25, "hour")),
    ("Pay rate: $70", (70.0, None, "hour")),
    ("$2,000 - $2,500 per week", (2000.0, 2500.0, "week")),
    # nonsense / traps
    ("$5/hr", None),
    ("$900 per hour", None),
    ("We raised $50 million in Series B funding.", None),
    ("$5,000 sign-on bonus!", None),
    ("$1,500 annual learning stipend", None),
    ("Salary $5,000 per year", None),
])
def test_pay(text, expected):
    assert parse_pay(text) == expected


# ------------------------------------------------------------------ duration

@pytest.mark.parametrize("text, expected", [
    ("6 month contract", 6),
    ("Duration: 12+ months", 12),
    ("Contract length: 3-6 months", 3),
    ("1 year contract", 12),
    ("This is a six-month contract", 6),
    ("12 week contract assignment", 3),
    ("Long term contract", None),
    ("3+ years of experience with Python", None),
    ("5 years of experience; this is a 6-12 month engagement", 6),
    ("within 6 months you will own the roadmap", None),
    ("The duration of this role is an 18 month contract. Onsite 4-6 weeks first.", 18),
    ("lead activities during the first 6-9 months. This is a 12 month contract", 12),
    ("Contract duration: 3-6 months initially", 3),
    ("This role is a 6-month contract to hire in Saint Louis, MO", 6),
    ("6 months of experience with PC hardware troubleshooting required", None),
])
def test_duration(text, expected):
    assert parse_duration_months(text) == expected


# ---------------------------------------------------------------- tax terms

@pytest.mark.parametrize("text, expected", [
    ("W2 only", ["w2"]),
    ("Open to W2 or C2C", ["w2", "c2c"]),
    ("Corp-to-Corp ok", ["c2c"]),
    ("1099 contractors welcome", ["1099"]),
    ("No C2C. W2 candidates only", ["w2"]),
    ("Prepare W-2 forms and 1099-MISC reporting", []),
    ("Must be able to work on our W-2", ["w2"]),
])
def test_tax_terms(text, expected):
    assert tax_terms_from_text(text) == expected


# --------------------------------------------------------------- visa terms

@pytest.mark.parametrize("text, expected", [
    ("USC only", ["usc_only"]),
    ("US Citizens only due to federal contract", ["usc_only"]),
    ("USC/GC only", ["usc_gc_only"]),
    ("GC holders only", ["usc_gc_only"]),
    ("USC, GC, GC-EAD, H4-EAD welcome", ["gc_ead_ok"]),
    ("GC/EAD ok", ["gc_ead_ok"]),
    ("H1B ok", ["h1b_ok"]),
    ("H-1B candidates welcome", ["h1b_ok"]),
    ("H-1B transfer is fine", ["h1b_transfer"]),
    ("No C2C", ["no_c2c"]),
    ("W2 only", ["no_c2c"]),
    ("We are unable to sponsor visas for this role.", ["no_sponsorship"]),
    ("No sponsorship available.", ["no_sponsorship"]),
    ("Must be authorized to work in the US without sponsorship.", ["no_sponsorship"]),
    ("We will sponsor H-1B visas for the right candidate.", ["sponsorship_available"]),
    ("Visa sponsorship is available.", ["sponsorship_available"]),
    ("Active Secret clearance required", ["security_clearance"]),
    ("TS/SCI with polygraph", ["security_clearance"]),
    ("Clearance required", ["security_clearance"]),
    ("No clearance required", []),
    ("We cannot sponsor H1B at this time", ["no_sponsorship"]),
    ("Sales clearance event every Friday", []),
])
def test_visa_terms(text, expected):
    assert visa_terms_from_text(text) == expected


def test_w2_only_sets_tax_and_no_c2c():
    out = classify("Java Developer", "Contract role. W2 only.", "Austin, TX")
    assert out["tax_terms"] == ["w2"] and "no_c2c" in out["visa_terms"]


# ------------------------------------------------------------------- is_us

@pytest.mark.parametrize("location, title, expected", [
    ("Austin, TX", None, True),
    ("Remote - US", None, True),
    ("United States", None, True),
    ("USA", None, True),
    ("New York, NY; London, UK", None, True),
    ("Remote", None, None),
    ("", None, None),
    ("Toronto, ON", None, False),
    ("Bengaluru, India", None, False),
    ("Chennai, TN, India", None, False),
    ("London", None, False),
    ("Dublin, CA", None, True),
    ("Remote", "Software Engineer (US)", True),
    ("Remote", "Account Executive - EMEA", False),
    ("Mexico City", None, False),
    ("Albuquerque, New Mexico", None, True),
    ("Cambridge, MA", None, True),
    ("Anywhere", None, None),
])
def test_is_us(location, title, expected):
    assert is_us_location(location, title) == expected


# ------------------------------------------------------------ full postings

def test_staffing_posting_end_to_end():
    html = """<p><b>Job Title:</b> Senior .NET Developer</p>
    <p>Location: Remote (US)</p><p>Duration: 12+ months</p>
    <p>Rate: $70-$80/hr on W2 or C2C</p><p>Visa: USC, GC, GC-EAD, H1B ok. No OPT.</p>"""
    out = classify("Senior .NET Developer", html, "Remote (US)", {"employment_type_raw": "Contract"})
    assert out == {
        "employment_type": "contract", "tax_terms": ["w2", "c2c"],
        "pay_rate_min": 70.0, "pay_rate_max": 80.0, "pay_period": "hour",
        "contract_duration_months": 12, "visa_terms": ["gc_ead_ok", "h1b_ok"], "countries": ["US"],
    }


def test_fte_posting_stays_clean():
    html = """<p>We're hiring a Staff Engineer to own contract negotiation tooling for our legal team.</p>
    <p>The base salary range is $180,000 - $220,000 per year plus equity.</p>
    <p>As a federal contractor, Acme is an equal opportunity employer. We are unable to sponsor visas.</p>"""
    out = classify("Staff Engineer, Legal Tools", html, "San Francisco, CA", {"employment_type_raw": "Full-time"})
    assert out["employment_type"] == "full_time" and out["tax_terms"] is None
    assert (out["pay_rate_min"], out["pay_rate_max"], out["pay_period"]) == (180000.0, 220000.0, "year")
    assert out["visa_terms"] == ["no_sponsorship"] and out["contract_duration_months"] is None


def test_structured_pay_is_preferred_and_validated():
    out = classify("Contractor", "", "Denver, CO", {"pay_rate_min": 90, "pay_rate_max": 110, "pay_period": "hourly"})
    assert (out["pay_rate_min"], out["pay_rate_max"], out["pay_period"]) == (90.0, 110.0, "hour")
    bad = classify("Contractor", "$60/hr", "Denver, CO", {"pay_rate_min": 90000, "pay_period": "hour"})
    assert (bad["pay_rate_min"], bad["pay_period"]) == (60.0, "hour")  # nonsense structured value rejected


def test_classifier_never_raises_on_odd_input():
    for args in [(None, None, None, None), ("", "<<<>>>", 123, {"extra": "x"}), ("x" * 5000, "$" * 1000, "US", {})]:
        classify(*args)


# ------------------------------------------------------------------ routing rule

@pytest.mark.parametrize("title, description, raw, staffing, expected", [
    # seasonal / fixed-term retail direct hires stay in jobs, labelled temporary
    ("Seasonal Stock & Fulfillment", "Join Kohl's for the holiday season! Pay: $15.50/hr. Store discount.", None, False,
     (False, "temporary")),
    ("Seasonal Sales Support", "Help guests this holiday season. $16 - $18 per hour.", None, False, (False, "temporary")),
    ("Guest Services Representative (Seasonal - Fixed Term)", "Nordstrom seasonal role through January.",
     {"employment_type_raw": "Seasonal - Fixed Term"}, False, (False, "temporary")),
    ("Seasonal Retail Associate", "Temporary position for the holidays.", None, False, (False, "temporary")),
    ("Store Associate", "", {"employment_type_raw": "Temporary"}, False, (False, "temporary")),
    # temporary with contract evidence -> contracts
    ("Temporary Software Engineer", "Temp role via TEKsystems, W2 $70/hr.", None, False, (True, "temporary")),
    ("Temporary Data Analyst", "3 month contract assignment. $55/hr.", None, False, (True, "temporary")),
    ("Temporary Accountant", "Temp assignment paying $40/hr on a contract basis.", None, False, (True, "temporary")),
    ("Seasonal Warehouse Associate", "$18/hr", None, True, (True, "temporary")),  # staffing source
    # always routed
    ("Java Developer (Contract)", "", None, False, (True, "contract")),
    ("QA Analyst (C2H)", "", None, False, (True, "contract_to_hire")),
    ("Freelance Copywriter", "", None, False, (True, "freelance")),
    # never routed
    ("Staff Engineer", "Full-time, benefits.", {"employment_type_raw": "Full-time"}, False, (False, "full_time")),
    ("Software Engineering Intern", "", None, False, (False, "internship")),
])
def test_contract_routing(title, description, raw, staffing, expected):
    assert contract_routing(title, description, raw, staffing=staffing) == expected


# Years of experience must never be read as a contract term.
import pytest as _pytest
from contracts.classifier import parse_duration_months as _dur


@_pytest.mark.parametrize("text,known,expected", [
    ("Requirements: 5+ years in Python and AWS", True, None),
    ("5+ years with Kubernetes; 12 month contract", True, 12),
    ("Duration: 1 year", True, 12),
    ("This is a 2 year contract W2", True, 24),
    ("1-year assignment with possible extension", True, 12),
    ("6-12 months contract", True, 6),
    ("Contract length: 18 months", False, 18),
    ("Must have 10 years building distributed systems", True, None),
    ("3+ years' experience", True, None),
])
def test_years_of_experience_are_not_durations(text, known, expected):
    assert _dur(text, known) == expected


# ------------------------------------------- company boards: ATS field or title only

REDDIT_PRIVACY = (
    "<p>Reddit is proud to be an equal opportunity employer.</p><p>Pay Transparency: $317,000 per year.</p>"
    "<p>Please see our Candidate Privacy Policy. By applying, you acknowledge that Reddit will collect "
    "and process your personal information to evaluate your application for employment or an "
    "independent contractor role, as applicable.</p>"
)


@pytest.mark.parametrize("title, description, raw, expected", [
    # the prod misroute: privacy boilerplate mentions "independent contractor role"
    ("Senior Director, Data Science", REDDIT_PRIVACY, None, (False, None)),
    ("Senior Director, Data Science", REDDIT_PRIVACY, {"employment_type_raw": "Full-time"}, (False, "full_time")),
    # description text never routes a company-board posting, even when it is explicit
    ("Data Engineer", "This is a 6 month contract role, W2 $70/hr.", None, (False, None)),
    ("Backend Engineer", "Contract-to-hire opportunity. C2C welcome.", None, (False, None)),
    ("Software Engineer", "We hire employees and contractors worldwide.", None, (False, None)),
    ("Recruiter", "Independent contractors are not eligible for benefits.", None, (False, None)),
    ("Designer", "You may be engaged as an employee or independent contractor.", None, (False, None)),
    ("Staff Engineer", "This is a full-time role with benefits.", None, (False, "full_time")),
    # (a) structured ATS field
    ("Data Engineer", "", {"employment_type_raw": "Contract"}, (True, "contract")),
    ("Data Engineer", "", {"employment_type_raw": "Contract to Hire"}, (True, "contract_to_hire")),
    ("Data Engineer", "", {"employment_type_raw": "Freelance"}, (True, "freelance")),
    ("Data Engineer", "", {"employment_type_raw": "Temporary (Contract)"}, (True, "contract")),
    ("Data Engineer", "", {"employment_type_raw": "Temp - W2"}, (True, "temporary")),
    ("Data Engineer", "", {"employment_type_raw": "Temporary"}, (False, "temporary")),
    ("Data Engineer", "", {"employment_type_raw": "Fixed Term"}, (False, "temporary")),
    ("Data Engineer", "6 month contract", {"employment_type_raw": "FullTime"}, (False, "full_time")),
    # (b) explicit title markers
    ("Java Developer (Contract)", "", {"employment_type_raw": "Full-time"}, (True, "contract")),
    ("Contractor - Data Analyst", "", None, (True, "contract")),
    ("QA Analyst C2H", "", None, (True, "contract_to_hire")),
    ("Contract-to-Hire Java Engineer", "", None, (True, "contract_to_hire")),
    ("Temp Receptionist", "", None, (True, "temporary")),
    ("Temporary Accountant", "", None, (True, "temporary")),
    ("Freelance Copywriter", "", None, (True, "freelance")),
    ("Real Estate Associate Agent (1099) - Boise", "", None, (True, "contract")),
    ("Data Engineer (Contract)", "", {"employment_type_raw": "Contract to Hire"}, (True, "contract_to_hire")),
    # not markers
    ("Seasonal Stock & Fulfillment", "Temporary position", None, (False, "temporary")),
    ("Contract Manager", "", None, (False, None)),
    ("Government Contracts Analyst", "", None, (False, None)),
    ("Frontend Engineer, Ads Campaign Manager", "employment or an independent contractor role", None, (False, None)),
])
def test_company_board_routing(title, description, raw, expected):
    assert contract_routing(title, description, raw) == expected


@pytest.mark.parametrize("text", [
    "We evaluate your application for employment or an independent contractor role, as applicable.",
    "Our employees and contractors enjoy flexible hours.",
    "This policy applies to employees, interns and contractors.",
    "Whether as an employee or independent contractor, you must comply.",
    "Independent contractors are not eligible for the bonus program.",
    "Contractors or employees must complete training.",
    "Equal Opportunity Employer: contractors and applicants are considered without regard to race.",
])
def test_boilerplate_never_reads_as_contract(text):
    assert employment_type_from_text(text) is None
    # staffing text detection too
    assert detect_employment_type("Analyst", text) is None


def test_boilerplate_keeps_real_contract_sentences():
    text = ("This is a 6 month contract role. We are an equal opportunity employer and evaluate applications "
            "for employment or an independent contractor role.")
    assert employment_type_from_text(text) == "contract"
    assert contract_routing("Analyst", text, staffing=True) == (True, "contract")


# ------------------------------------- "contract" as the subject of the work, not the terms

@pytest.mark.parametrize("title", [
    "Smart Contract Engineer", "Smart Contracts Developer", "Senior Smart Contract Auditor",
    "Contract Management Specialist", "Contract Manager", "Contracts Administrator", "Contract Analyst",
    "Contracts Systems Analyst", "Government Contracts Manager", "Contract Negotiation Lead",
    "Contract Review Attorney", "Contract Lifecycle Manager", "CLM Contract Administrator", "CLM Developer",
])
@pytest.mark.parametrize("staffing", [False, True])
def test_contract_work_titles_are_not_contract_terms(title, staffing):
    route, et = contract_routing(title, "", None, staffing=staffing)
    assert not route and et is None


@pytest.mark.parametrize("title, expected", [
    ("Smart Contract Engineer (Contract)", (True, "contract")),
    ("Contract - Smart Contract Engineer", (True, "contract")),
    ("Contract Manager (Contract)", (True, "contract")),
    ("Contract Java Developer", (True, "contract")),
    ("Contracts Systems Analyst - 6 month contract", (True, "contract")),
])
def test_real_contract_markers_still_route(title, expected):
    assert contract_routing(title) == expected


@pytest.mark.parametrize("text, expected", [
    ("We build smart contracts on Ethereum.", None),
    ("This is a smart contract role on our DeFi team.", None),
    ("Experience with contract lifecycle management (CLM) tools such as Icertis.", None),
    ("This is a contract management position supporting government contracts.", None),
    ("Support contract negotiation and contract review for vendor contracts.", None),
    ("This is a 6 month contract role auditing smart contracts.", "contract"),
])
def test_contract_work_in_description(text, expected):
    assert employment_type_from_text(text) == expected
