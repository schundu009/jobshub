"""services.firm_matching: work type, search terms, locations, skills matching, TTL cache."""
import pytest

from services import firm_matching as fm


@pytest.mark.parametrize("title,location,desc,expected", [
    ("Backend Engineer", "Remote - US", None, "remote"),
    ("Backend Engineer (Remote)", "San Francisco, CA", None, "remote"),
    ("Backend Engineer", "Hybrid - Palo Alto, CA", None, "hybrid"),
    ("Backend Engineer", "New York, NY", "This is a hybrid role with 3 days a week in office.", "hybrid"),
    ("Backend Engineer", "New York, NY", "You'll spend two days per week in the office.", "hybrid"),
    ("Backend Engineer", "", "<p>We are a <b>fully remote</b> team.</p>", "remote"),
    ("Backend Engineer", "", "This position is on-site in our lab.", "onsite"),
    ("Backend Engineer", "", "Work in-office with the team.", "onsite"),
    ("Backend Engineer", "Austin, TX", "Build services.", "onsite"),
    ("Backend Engineer", "Multiple Locations", None, None),
    ("Backend Engineer", None, None, None),
    # "distributed" / "hybrid cloud" in a title are about the work, not where it happens
    ("Distributed Systems Engineer", "Seattle, WA", None, "onsite"),
    ("Hybrid Cloud Engineer", "Denver, CO", "Design hybrid cloud networks.", "onsite"),
])
def test_derive_work_type(title, location, desc, expected):
    assert fm.derive_work_type(title, location, desc) == expected


def test_normalize_employment():
    assert fm.normalize_employment(None) == "full_time"
    assert fm.normalize_employment("") == "full_time"
    assert fm.normalize_employment("Full-time") == "full_time"
    assert fm.normalize_employment("part time") == "part_time"
    assert fm.normalize_employment("intern") == "internship"
    assert fm.normalize_employment("seasonal") == "temporary"


def test_resolve_location_labels_and_keys():
    assert "palo alto" in fm.resolve_location("San Francisco Bay Area")
    assert fm.resolve_location("  san francisco   bay area ") == fm.resolve_location("sf")
    assert fm.resolve_location("Denver / Boulder") == ("denver", "boulder")
    assert "brooklyn" in fm.resolve_location("New York City")
    assert fm.resolve_location("Portland, OR") is None
    # every metro label the page sends resolves
    for label in ("San Francisco Bay Area", "New York City", "Seattle area", "Los Angeles", "Austin", "Boston",
                  "Chicago", "Denver / Boulder"):
        assert fm.resolve_location(label)


def test_search_terms_and_word_regex():
    assert fm.search_terms("  Go  Backend, go ") == [("go", True), ("backend", False)]
    assert fm.search_terms("c++ k8s") == [("c++", True), ("k8s", True)]
    import re
    rx = re.compile(fm.word_regex("go"))
    assert rx.search("senior go engineer") and rx.search("go") and rx.search('["go", "aws"]')
    assert not rx.search("google") and not rx.search("django")


def test_role_resolution_labels():
    p = fm.build_profile("backend, Site Reliability Engineer, backend", "", None)
    assert [r.label for r in p.roles] == ["Backend Engineer", "Site Reliability Engineer"]
    assert p.roles[1].group == "sre"


def test_score_weights_and_reasons():
    p = fm.build_profile("backend", "go,k8s,aws,python,terraform,react,kafka,rust", "senior")
    score, reasons = fm.score_job("Senior Backend Engineer", ["Go", "Kubernetes", "AWS", "Python"], p)
    # title 55 + skills 35 * 4/8 + seniority 10
    assert score == round(55 + 35 * 4 / 8 + 10)
    assert reasons == ["Title matches Backend Engineer", "4 of 8 skills: go, k8s, aws, python", "Senior level"]
    # skills come from the title too
    _, reasons = fm.score_job("Backend Engineer (Go)", [], p)
    assert any(r.startswith("1 of 8 skills: go") for r in reasons)


def test_skills_only_is_80_20():
    p = fm.build_profile("", "go,aws", "senior")
    score, reasons = fm.score_job("Senior Engineer", ["go"], p)
    assert score == round((80 * 0.5 + 20 * 1.0))
    assert fm.max_score_without_skills(p) == pytest.approx(20.0)
    p2 = fm.build_profile("", "go,aws", None)
    assert fm.score_job("Engineer", ["go", "aws"], p2)[0] == 100
    assert fm.score_job("Engineer", [], p2)[0] == 0


def test_inactive_profile_scores_none():
    assert fm.score_job("Anything", ["go"], fm.build_profile("", "", "senior")) == (None, None)


def test_title_word_sets_are_superset_of_scored_titles():
    p = fm.build_profile("backend,devops", "", None)
    sets = fm.role_title_word_sets(p.roles)
    for title in ("Senior Backend Engineer", "Full-Stack Developer", "Site Reliability Engineer", "DevOps Lead"):
        if fm.score_job(title, [], p)[0] > 0:
            low = title.lower()
            assert any(all(w in low for w in ws) for ws in sets), title
    # reduced: no kept set contains another
    for a in sets:
        assert not any(b != a and set(b) <= set(a) for b in sets)


def test_ttl_cache_expiry_and_lru():
    c = fm.TTLCache(maxsize=2, ttl=60)
    c.set("a", 1)
    c.set("b", 2)
    assert c.get("a") == 1
    c.set("c", 3)  # evicts b (least recently used)
    assert c.get("b") is None and c.get("a") == 1 and c.get("c") == 3
    c.set("d", 4, ttl=-1)
    assert c.get("d") is None
    c.clear()
    assert c.get("a") is None
