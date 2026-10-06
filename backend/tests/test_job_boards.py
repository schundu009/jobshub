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
    ("https://careers-acme.icims.com/jobs/1234/engineer/job", ("icims", "careers-acme.icims.com")),
    ("https://internal-acme.icims.com/jobs/search", None),
    ("https://www2.jobdiva.com/portal/?a=tmjdnw195lqt8n1w5asw8r4q3j2ixr002cwt3sf&amp;compid=0#/",
     ("jobdiva", "www2.tmjdnw195lqt8n1w5asw8r4q3j2ixr002cwt3sf")),
    ("https://www1.jobdiva.com/candidates/myjobs/searchjobsdone.jsp?a=qfjdnwj6ytav36y4wncfts29u9d&compid=-1",
     ("jobdiva", "www1.qfjdnwj6ytav36y4wncfts29u9d")),
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


def test_board_with_max_age_keeps_only_recent_postings(boards_db, monkeypatch):
    """job_boards.max_age_days: postings first published before the cutoff are not
    saved, and ones that age past it are closed. Greenhouse dates by first_published."""
    from datetime import timedelta
    from tasks import scraper_tasks
    row = add_board(boards_db)
    row.max_age_days = 3
    boards_db.commit()
    now = datetime.utcnow()
    iso = lambda d: (now - timedelta(days=d)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def posting(i, first, updated):
        return {"id": i, "title": "Platform Engineer", "location": {"name": "Remote"},
                "absolute_url": f"https://job-boards.greenhouse.io/acme/jobs/{i}", "content": "Build it.",
                "first_published": iso(first), "updated_at": iso(updated)}

    # Job 2 was updated yesterday but first published 40 days ago: not recent.
    jobs = [posting(1, 1, 1), posting(2, 40, 1)]

    async def fetch_json(self, url, method="GET", params=None, json_data=None, **_):
        return {"jobs": jobs}
    monkeypatch.setattr(BoardScraper, "fetch_json", fetch_json)
    out = scraper_tasks.scrape_company_http.run("acmeboard")
    assert out["status"] == "success" and out["jobs_new"] == 1
    saved = boards_db.query(Job).filter(Job.source == "acmeboard").one()
    assert saved.external_job_id == "1"

    # Four days on, job 1 is past the cutoff: the next run closes it.
    saved.posted_date = now - timedelta(days=4)
    boards_db.commit()
    jobs[:] = [posting(3, 0, 0)]
    scraper_tasks.scrape_company_http.run("acmeboard")
    boards_db.expire_all()
    active = {j.external_job_id for j in boards_db.query(Job).filter(Job.source == "acmeboard", Job.is_active == True)}  # noqa: E712
    assert active == {"3"}


def test_icims_and_successfactors_boards_reuse_the_mixins():
    from scrapers.enterprise.icims_scrapers import ICIMSMixin
    from scrapers.enterprise.successfactors_scrapers import SuccessFactorsMixin
    ic = build_scraper_class({"slug": "icco", "company_name": "IC Co", "ats": "icims",
                              "board": "careers-icco.icims.com", "careers_url": None})
    assert issubclass(ic, ICIMSMixin) and ic.ICIMS_HOST == "careers-icco.icims.com"
    assert ic.config.careers_url == "https://careers-icco.icims.com/jobs/search"
    sf = build_scraper_class({"slug": "sfco", "company_name": "SF Co", "ats": "successfactors",
                              "board": "jobs.sfco.com", "careers_url": None})
    assert issubclass(sf, SuccessFactorsMixin) and sf.SF_HOST == "jobs.sfco.com"
    assert api_url("icims", "evil.example.com") is None
    assert api_url("successfactors", "not a host") is None


def test_jobdiva_board_scrapes_with_the_portal_token(monkeypatch):
    """JobDiva: anonymous portal token first, then the paged job search."""
    import asyncio
    board = "www2.tmjdnw195lqt8n1w5asw8r4q3j2ixr002cwt3sf"
    cls = build_scraper_class({"slug": "divaco", "company_name": "Diva Co", "ats": "jobdiva",
                               "board": board, "careers_url": None})
    assert cls.config.careers_url == "https://www2.jobdiva.com/portal/?a=tmjdnw195lqt8n1w5asw8r4q3j2ixr002cwt3sf"
    assert api_url("jobdiva", "www3.bad") is None
    calls = []

    async def request(self, method, url, read, **kwargs):
        calls.append((method, url.rsplit("/", 2)[-2:], kwargs.get("headers", {}).get("token")))
        if url.endswith("/auth/a"):
            return {"token": "T1", "portalID": 44}
        return {"total": 1, "data": [{"id": 7, "title": "DevOps Engineer", "location": "Austin, TX",
                                      "postDate": 1789488443000, "jobDescription": "Kubernetes.",
                                      "positionType": "Contract"}]}
    monkeypatch.setattr(BoardScraper, "_request", request)
    result = asyncio.run(cls().scrape())
    assert result.success and result.complete and result.jobs_found == 1
    job = result.jobs[0]
    assert job.job_url.endswith("#/jobs/7") and job.employment_type_raw == "Contract"
    assert job.posted_date == datetime(2026, 9, 15, 16, 7, 23)
    assert calls[0][2] is None and calls[1][2] == "T1"  # token only on the search


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


def test_redetect_moves_a_board_to_its_new_ats(client, db, admin_headers, no_dispatch, monkeypatch):
    from models import ScraperConfigDB
    add_board(db, slug="movedco", ats="lever", board="movedco", name="Moved Co")
    db.add(ScraperConfigDB(company_slug="movedco", is_enabled=False, consecutive_failures=575,
                           config_overrides={"auto_disabled": True, "auto_disabled_reason": "404"}))
    db.commit()
    # The careers page finds nothing; the same token answers on Ashby.
    _detected(monkeypatch, None)
    monkeypatch.setattr(ats_detect, "probe", lambda ats, board: 120 if ats == "ashby" else 0)
    resp = client.post("/api/scrapers/custom/movedco/redetect", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["previous"] == {"ats": "lever", "board": "movedco"}
    assert (body["ats"], body["board"], body["job_count"]) == ("ashby", "movedco", 120)
    assert no_dispatch == [(["movedco"], "scrapers_http")]
    db.expire_all()
    row = db.query(JobBoard).filter_by(slug="movedco").one()
    assert (row.ats, row.board, row.enabled) == ("ashby", "movedco", True)
    cfg = db.query(ScraperConfigDB).filter_by(company_slug="movedco").one()
    assert cfg.is_enabled is True and cfg.consecutive_failures == 0 and "auto_disabled" not in cfg.config_overrides


def test_redetect_re_enables_a_board_that_works_again(client, db, admin_headers, no_dispatch, monkeypatch):
    from models import ScraperConfigDB
    add_board(db, slug="backco", ats="ashby", board="backco")
    db.add(ScraperConfigDB(company_slug="backco", is_enabled=False, consecutive_failures=575))
    db.commit()
    _detected(monkeypatch, None)
    monkeypatch.setattr(ats_detect, "probe", lambda ats, board: 120 if ats == "ashby" else 0)
    body = client.post("/api/scrapers/custom/backco/redetect", headers=admin_headers).json()
    assert body["previous"] == {"ats": "ashby", "board": "backco"} and body["ats"] == "ashby"
    db.expire_all()
    cfg = db.query(ScraperConfigDB).filter_by(company_slug="backco").one()
    assert cfg.is_enabled is True and cfg.consecutive_failures == 0
    assert no_dispatch == [(["backco"], "scrapers_http")]


def test_redetect_refuses_unknown_coded_and_unfindable(client, db, admin_headers, no_dispatch, monkeypatch):
    assert client.post("/api/scrapers/custom/nope/redetect", headers=admin_headers).status_code == 404
    assert client.post("/api/scrapers/custom/circleci/redetect", headers=admin_headers).status_code == 400
    add_board(db, slug="lostco", ats="lever", board="lostco")
    _detected(monkeypatch, None)
    monkeypatch.setattr(ats_detect, "probe", lambda ats, board: 0)
    assert client.post("/api/scrapers/custom/lostco/redetect", headers=admin_headers).status_code == 400
    # A board another company already owns is refused.
    add_board(db, slug="owner", ats="ashby", board="lostco")
    monkeypatch.setattr(ats_detect, "probe", lambda ats, board: 5 if ats == "ashby" else 0)
    assert client.post("/api/scrapers/custom/lostco/redetect", headers=admin_headers).status_code == 409
    assert no_dispatch == []


def test_delete_board_only(client, db, admin_headers):
    add_board(db, slug="gone")
    db.add(ScraperRun(company_slug="gone", success=True, jobs_found=1, run_at=datetime.utcnow()))
    db.commit()
    assert client.delete("/api/scrapers/custom/gone", headers=admin_headers).json()["status"] == "deleted"
    assert db.query(JobBoard).count() == 0 and db.query(ScraperRun).count() == 0
    assert client.delete("/api/scrapers/custom/circleci", headers=admin_headers).status_code == 400
    assert client.delete("/api/scrapers/custom/nosuch", headers=admin_headers).status_code == 404
