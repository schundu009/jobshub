# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## CRITICAL: Deployment After Every Change

This is a PRODUCTION project. ALL code changes MUST be deployed immediately.

```bash
git add -A && git commit -m "Your message" && git push origin main
```

**DO NOT** consider a task complete until changes are committed and pushed.

### Production URLs
- **Frontend**: https://www.cariara.com/jobs/
- **Backend API**: https://cariara-backend.up.railway.app
- **Admin Portal**: https://www.cariara.com/admin/

Railway and Vercel auto-deploy from `main` branch within 1-2 minutes.

## Development Commands

```bash
# Activate virtual environment
source venv/bin/activate

# Start backend (with auto-reload)
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Serve frontend (separate terminal)
cd frontend && python3 -m http.server 3000

# Run tests
pytest

# Format code
black backend/
isort backend/

# Database migrations
alembic revision --autogenerate -m "description"
alembic upgrade head

# Celery worker (requires Redis)
celery -A backend.celery_app worker --loglevel=info

# Celery scheduler
celery -A backend.celery_app beat --loglevel=info

# Install Playwright browsers (for scraping)
playwright install chromium
```

## Service Health Verification

Always verify services after code changes:
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/analytics/summary
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/
pgrep -fl "uvicorn"
```

## Architecture Overview

### Backend (FastAPI)
- **Entry**: `backend/main.py` - FastAPI app setup with CORS, routes, static files
- **Database**: SQLite (local `data/jobtrails.db`) / PostgreSQL (Railway production)
- **ORM**: SQLAlchemy 2.0 with all models in `backend/models.py`
- **Auth**: JWT tokens with OAuth 2.0 (Google, GitHub, LinkedIn) in `routes/auth.py` and `routes/oauth.py`

### Frontend (Vanilla HTML/CSS/JS)
- **Auth helper**: `frontend/js/app.js` - Use `apiRequest()` for all API calls (handles auth, token refresh)
- **Theme**: Dark/light mode via `data-theme` attribute
- Pages: `index.html` (dashboard), `jobs.html` (list), `discover.html` (ATS discovery), `analytics.html`

### Scraper System
Located in `backend/scrapers/`, uses a mixin-based architecture:

**Base Classes** (`base.py`):
- `HTTPScraper` - For sites with JSON APIs (most common)
- `PlaywrightScraper` - For JavaScript-heavy sites requiring browser

**ATS Mixins** (provide `scrape()` and `parse_job()` implementations):
- `GreenhouseMixin` - boards-api.greenhouse.io
- `AshbyMixin` - api.ashbyhq.com
- `LeverMixin` - jobs.lever.co
- `WorkdayHybridMixin` - Workday sites (requires Playwright)
- `SmartRecruitersMixin` - SmartRecruiters ATS

**Adding a scraper**:
```python
@ScraperRegistry.register(category="custom")
class CompanyScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="slug", company_name="Name", ...)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/slug/jobs"
```

### Background Tasks (Celery)
- **Broker**: Redis
- **Task Queues**: `scrapers_http`, `scrapers_browser`, `scrapers_orchestrator`, `maintenance`
- **Scheduled**: `scrape_all_companies` runs every 6 hours via Beat

## Auto-Apply Feature

Only works with: **Greenhouse**, **Lever**, **Workday**
NOT supported: Ashby, iCIMS, Taleo, BrassRing, Jobvite, SmartRecruiters

Key endpoints:
- `POST /api/auto-apply/submit/{job_id}` - Submit application
- `GET /api/auto-apply/preflight/{job_id}` - Check availability

## Railway Services

| Service | Purpose | Dockerfile |
|---------|---------|------------|
| Backend | FastAPI API | `Dockerfile` |
| Worker | Celery tasks | `Dockerfile.worker` |
| Beat | Task scheduler | `Dockerfile.beat` |
| Redis | Queue broker | Railway managed |
| PostgreSQL | Database | Railway managed |

## Common Issues

### Railway SSL Errors
For internal PostgreSQL connections, ensure `sslmode=disable`:
```python
if 'railway.internal' in db_url and '?' not in db_url:
    db_url = f"{db_url}?sslmode=disable"
```

### OAuth redirect_uri_mismatch
Set `BACKEND_URL=https://cariara-backend.up.railway.app` (not `cariara-backend-production`)

### Frontend "Loading..." Stuck
Use `apiRequest('/jobs/${jobId}')` from `app.js`, not raw `fetch()`

### Playwright Browser Missing
In `Dockerfile.worker`:
```dockerfile
RUN playwright install --with-deps chromium chromium-headless-shell
```

### Workday URL Case Sensitivity
Site names like `External_Career` must preserve case - don't lowercase

### Company Moved to Different ATS
Common migrations (update scraper to use new API):
- Anyscale: Greenhouse → Ashby
- Character AI: Greenhouse → Ashby
