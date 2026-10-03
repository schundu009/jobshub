"""Companies as data: job_boards rows, the ATS detector, the registry fallback and the admin add route."""
import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import sessionmaker

from models import Job, JobBoard, ScraperRun, User
from scrapers import board_scraper
from scrapers.board_scraper import BoardScraper, api_url, build_scraper_class
from scrapers.registry import ScraperRegistry, get_scraper
from services import ats_detect
from utils.security import create_access_token, hash_password


@pytest.fixture(autouse=True)
def _no_dns(monkeypatch):
    """The SSRF check resolves hostnames; keep these tests offline."""
    import socket
    from utils import security

    def gaierror(*_a, **_k):
        raise socket.gaierror("offline test")
    monkeypatch.setattr(security.socket, "getaddrinfo", gaierror)


@pytest.fixture
def boards_db(db, monkeypatch):
    """Point the code that opens its own sessions (registry, tasks) at the test engine."""
    import database
    from tasks import scraper_tasks
    factory = sessionmaker(bind=db.get_bind())
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setattr(scraper_tasks, "SessionLocal", factory)
    monkeypatch.setattr(scraper_tasks, "get_db", factory)
    return db


def add_board(db, slug="acmeboard", ats="greenhouse", board="acme", name="Acme Board", enabled=True):
    row = JobBoard(company_name=name, slug=slug, ats=ats, board=board, enabled=enabled,
                   careers_url=f"https://example.com/{slug}")
    db.add(row)
    db.commit()
    return row


# ------------------------------------------------------------------ detector

@pytest.mark.parametrize("url,expected", [
    ("https://boards.greenhouse.io/Acme", ("greenhouse", "acme")),
    ("https://job-boards.greenhouse.io/acme/jobs/123", ("greenhouse", "acme")),
    ("https://boards.greenhouse.io/embed/job_board?for=acme", ("greenhouse", "acme")),
    ("https://boards-api.greenhouse.io/v1/boards/acme/jobs", ("greenhouse", "acme")),
    ("https://jobs.lever.co/acme/abc-123", ("lever", "acme")),
    ("https://jobs.ashbyhq.com/acme", ("ashby", "acme")),
    ("https://jobs.smartrecruiters.com/WesternDigital", ("smartrecruiters", "WesternDigital")),
    ("https://careers.smartrecruiters.com/Acme1", ("smartrecruiters", "Acme1")),
    ("https://acme.wd5.myworkdayjobs.com/Acme_Careers", ("workday", "acme.wd5.myworkdayjobs.com/acme/Acme_Careers")),
    ("https://acme.wd1.myworkdayjobs.com/en-US/External/job/x_R1", ("workday", "acme.wd1.myworkdayjobs.com/acme/External")),
    ("https://acme.wd1.myworkdayjobs.com/en-US", None),
    ("https://boards.greenhouse.io/embed/job_board", None),
    ("https://www.acme.com/careers", None),
])
def test_match_url(url, expected):
    assert ats_detect.match_url(url) == expected


def test_candidates_in_html_reads_links_and_scripts():
    html = """
      <a href="https://jobs.lever.co/acme">Open roles</a>
      <script src="//boards.greenhouse.io/embed/job_board/js?for=acme"></script>
      <a href="https://jobs.lever.co/acme/123">dup</a>
      <a href="https://linkedin.com/company/acme">no</a>
    """
    assert ats_detect.candidates_in_html(html, "https://acme.com/careers") == [
        ("lever", "acme"), ("greenhouse", "acme")]


def test_detect_url_pattern_then_probe(monkeypatch):
    probes = []
    monkeypatch.setattr(ats_detect, "probe", lambda ats, board: probes.append((ats, board)) or 12)
    monkeypatch.setattr(ats_detect, "_fetch_page", lambda url: pytest.fail("no page fetch for a board URL"))
    found = ats_detect.detect("https://jobs.ashbyhq.com/acme")
    assert found == {"ats": "ashby", "board": "acme",
                     "api_url": "https://api.ashbyhq.com/posting-api/job-board/acme", "job_count": 12}
    assert probes == [("ashby", "acme")]


def test_detect_page_links_and_requires_jobs(monkeypatch):
    html = '<a href="https://jobs.lever.co/acme">x</a><a href="https://boards.greenhouse.io/acme">y</a>'
    monkeypatch.setattr(ats_detect, "_fetch_page", lambda url: (url, html))
    counts = {("lever", "acme"): 0, ("greenhouse", "acme"): 5}
    monkeypatch.setattr(ats_detect, "probe", lambda ats, board: counts[(ats, board)])
    assert ats_detect.detect("https://acme.com/careers")["ats"] == "greenhouse"

    monkeypatch.setattr(ats_detect, "probe", lambda ats, board: 0)
    assert ats_detect.detect("https://acme.com/careers") is None
    monkeypatch.setattr(ats_detect, "_fetch_page", lambda url: None)
    assert ats_detect.detect("https://acme.com/careers") is None


@pytest.mark.parametrize("ats,data,count", [
    ("greenhouse", {"jobs": [{}, {}]}, 2),
    ("lever", [{}, {}, {}], 3),
    ("ashby", {"jobs": [{"isListed": True}, {"isListed": False}]}, 1),
    ("smartrecruiters", {"totalFound": 40, "content": [{}]}, 40),
    ("workday", {"total": 0, "jobPostings": []}, 0),
    ("workday", {"total": 7}, 7),
    ("greenhouse", "<html>", 0),
])
def test_job_count(ats, data, count):
    assert ats_detect._job_count(ats, data) == count


def test_ingestion_detect_ats_type_delegates():
    from services.ingestion_service import detect_ats_type
    assert detect_ats_type("https://boards.greenhouse.io/Acme") == ("greenhouse", "acme")
    assert detect_ats_type("https://jobs.smartrecruiters.com/WesternDigital") == ("smartrecruiters", "westerndigital")
    assert detect_ats_type("https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite") == (
        "workday", "nvidia:wd5:NVIDIAExternalCareerSite")
    assert detect_ats_type("https://apply.workable.com/acme") == ("workable", "acme")


# ------------------------------------------------------------------ board scraper

def test_api_urls():
    assert api_url("greenhouse", "acme") == "https://boards-api.greenhouse.io/v1/boards/acme/jobs"
    assert api_url("lever", "acme") == "https://api.lever.co/v0/postings/acme?mode=json"
    assert api_url("smartrecruiters", "Acme") == "https://api.smartrecruiters.com/v1/companies/Acme/postings"
    assert api_url("workday", "acme.wd5.myworkdayjobs.com/acme/Careers") == \
        "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/Careers/jobs"
    assert api_url("workday", "evil.com/acme/Careers") is None
    assert api_url("greenhouse", "a/b") is None
    assert api_url("icims", "acme") is None


def _board(**kw):
    return {"slug": "acmeboard", "company_name": "Acme", "ats": "greenhouse", "board": "acme",
            "careers_url": None, **kw}


def test_build_scraper_class_per_ats():
    sr = build_scraper_class(_board(ats="smartrecruiters", board="Acme"))
    assert sr.COMPANY_ID == "Acme" and issubclass(sr, BoardScraper)
    assert sr.config.careers_url == "https://jobs.smartrecruiters.com/Acme"
    wd = build_scraper_class(_board(slug="acmewd", ats="workday", board="acme.wd5.myworkdayjobs.com/acme/Careers"))
    assert wd.API_URL.endswith("/wday/cxs/acme/Careers/jobs")
    assert build_scraper_class(_board(ats="icims")) is None


def test_board_scraper_scrapes_with_the_mixin():
    cls = build_scraper_class(_board(slug="acmewd2", ats="workday", board="acme.wd5.myworkdayjobs.com/acme/Careers"))
    scraper = cls()

    async def fetch_json(url, method="GET", params=None, json_data=None, **_):
        assert method == "POST" and url == cls.API_URL
        return {"jobPostings": [{"title": "SRE", "externalPath": "/job/Austin/SRE_R1", "bulletFields": ["R1"]}]}
    scraper.fetch_json = fetch_json
    result = asyncio.run(scraper.scrape())
    assert result.success and result.jobs[0].job_url == "https://acme.wd5.myworkdayjobs.com/Careers/job/Austin/SRE_R1"


# ------------------------------------------------------------------ registry + tasks

def test_registry_falls_back_to_enabled_board_rows(boards_db):
    add_board(boards_db)
    add_board(boards_db, slug="offboard", enabled=False)
    add_board(boards_db, slug="circleci", board="circleci", name="CircleCI dup")  # coded slug: code wins

    cls = ScraperRegistry.get("acmeboard")
    assert cls is not None and cls.API_URL == "https://boards-api.greenhouse.io/v1/boards/acme/jobs"
    assert isinstance(get_scraper("acmeboard"), BoardScraper)
    meta = ScraperRegistry.get_metadata("acmeboard")
    assert meta["category"] == "boards" and meta["company_name"] == "Acme Board" and meta["ats"] == "greenhouse"
    assert ScraperRegistry.get("offboard") is None and ScraperRegistry.get("nosuch") is None
    assert not issubclass(ScraperRegistry.get("circleci"), BoardScraper)
    assert ScraperRegistry.list_board_slugs() == ["acmeboard"]


def test_registry_without_board_table_is_unchanged(monkeypatch):
    def broken():
        raise RuntimeError("no table")
    import database
    monkeypatch.setattr(database, "SessionLocal", broken)
    assert ScraperRegistry.get("acmeboard") is None
    assert ScraperRegistry.list_board_slugs() == []


def test_scrape_all_includes_boards(boards_db, monkeypatch):
    from tasks import scraper_tasks
    add_board(boards_db)
    monkeypatch.setattr(scraper_tasks, "_interval_gate", lambda force: None)
    monkeypatch.setattr(scraper_tasks.ScraperRegistry, "get_all", classmethod(lambda cls: {}))
    dispatched = []
    monkeypatch.setattr(scraper_tasks, "_dispatch_staggered",
                        lambda sigs, queue: dispatched.extend((queue, s.args[0]) for s in sigs))
    scraper_tasks.scrape_all_companies(force=True)
    assert dispatched == [("scrapers_http", "acmeboard")]


def test_scrape_company_http_saves_and_records_a_board(boards_db, monkeypatch):
    from tasks import scraper_tasks
    add_board(boards_db)

    async def fetch_json(self, url, method="GET", params=None, json_data=None, **_):
        return {"jobs": [{"id": 9, "title": "Platform Engineer", "location": {"name": "Remote"},
                          "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/9",
                          "content": "Build the platform.", "updated_at": "2026-09-30T00:00:00Z"}]}
    monkeypatch.setattr(BoardScraper, "fetch_json", fetch_json)
    out = scraper_tasks.scrape_company_http.run("acmeboard")
    assert out["status"] == "success" and out["jobs_new"] == 1
    job = boards_db.query(Job).filter(Job.source == "acmeboard").one()
    assert job.company.name == "Acme Board"
    run = boards_db.query(ScraperRun).filter_by(company_slug="acmeboard").one()
    assert run.success and run.jobs_found == 1


# ------------------------------------------------------------------ admin routes

@pytest.fixture
def admin_headers(db):
    user = User(email="boards-admin@example.com", name="a", role="admin", is_active=True,
                password_hash=hash_password("Test-password-123"))
    db.add(user)
    db.commit()
    token, _ = create_access_token(user.id, user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def no_dispatch(monkeypatch):
    from tasks import scraper_tasks
    queued = []
    monkeypatch.setattr(scraper_tasks.scrape_company_http, "apply_async",
                        lambda args=None, queue=None, **_: queued.append((args, queue)) or SimpleNamespace(id="t1"))
    return queued


def _detected(monkeypatch, found):
    monkeypatch.setattr(ats_detect, "detect", lambda url: found)


GH = {"ats": "greenhouse", "board": "newco", "api_url": api_url("greenhouse", "newco"), "job_count": 4}


def test_add_company_saves_a_board_row(client, db, admin_headers, no_dispatch, monkeypatch):
    _detected(monkeypatch, GH)
    resp = client.post("/api/scrapers/custom/add", headers=admin_headers,
                       json={"company_name": "New Co", "careers_url": "https://newco.example.com/careers"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["slug"] == "newco" and body["board_type"] == "greenhouse" and body["job_count"] == 4
    assert body["task_id"] == "t1" and no_dispatch == [(["newco"], "scrapers_http")]
    row = db.query(JobBoard).filter_by(slug="newco").one()
    assert (row.ats, row.board, row.enabled) == ("greenhouse", "newco", True)

    again = client.post("/api/scrapers/custom/add", headers=admin_headers,
                        json={"company_name": "New Co", "careers_url": "https://newco.example.com/careers"})
    assert again.status_code == 409
    same_board = client.post("/api/scrapers/custom/add", headers=admin_headers,
                             json={"company_name": "NewCo Labs", "careers_url": "https://newco.example.com/careers"})
    assert same_board.status_code == 409 and "newco" in same_board.json()["detail"]


def test_add_company_refuses_coded_slug_and_undetectable(client, admin_headers, no_dispatch, monkeypatch):
    _detected(monkeypatch, GH)
    coded = client.post("/api/scrapers/custom/add", headers=admin_headers,
                        json={"company_name": "CircleCI", "careers_url": "https://circleci.com/careers"})
    assert coded.status_code == 409
    _detected(monkeypatch, None)
    none = client.post("/api/scrapers/custom/add", headers=admin_headers,
                       json={"company_name": "Nothing Co", "careers_url": "https://nothing.example.com/jobs"})
    assert none.status_code == 400 and no_dispatch == []


def test_detect_route_shape(client, admin_headers, monkeypatch):
    _detected(monkeypatch, GH)
    body = client.post("/api/scrapers/custom/detect", headers=admin_headers,
                       json={"careers_url": "https://newco.example.com/careers"}).json()
    assert body == {"board_type": "greenhouse", "valid": True, "job_count": 4,
                    "api_url": GH["api_url"], "error": None}
    _detected(monkeypatch, None)
    body = client.post("/api/scrapers/custom/detect", headers=admin_headers,
                       json={"careers_url": "https://newco.example.com/careers"}).json()
    assert body["board_type"] == "unknown" and body["valid"] is False


def test_delete_board_only(client, db, admin_headers):
    add_board(db, slug="gone")
    db.add(ScraperRun(company_slug="gone", success=True, jobs_found=1, run_at=datetime.utcnow()))
    db.commit()
    assert client.delete("/api/scrapers/custom/gone", headers=admin_headers).json()["status"] == "deleted"
    assert db.query(JobBoard).count() == 0 and db.query(ScraperRun).count() == 0
    assert client.delete("/api/scrapers/custom/circleci", headers=admin_headers).status_code == 400
    assert client.delete("/api/scrapers/custom/nosuch", headers=admin_headers).status_code == 404
