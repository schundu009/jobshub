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

# Run single test file
pytest backend/tests/test_scrapers.py -v

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

# Monitor Celery tasks
celery -A backend.celery_app flower --port=5555

# Install Playwright browsers (for scraping)
playwright install chromium
```

## Service Health Verification

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
- **Auth**: JWT tokens (15-min expiry, 7-day refresh) with OAuth 2.0 (Google, GitHub, LinkedIn)
- **Routes**: `backend/routes/` - 17 route files including AI, analytics, auth, auto-apply, scrapers
- **Services**: `backend/services/` - Business logic layer

### Frontend (Vanilla HTML/CSS/JS)
- **Auth helper**: `frontend/js/app.js` - Use `apiRequest()` for all API calls (handles auth, token refresh)
- **Theme**: Dark/light mode via `data-theme` attribute
- Pages: `index.html` (dashboard), `jobs.html` (list), `discover.html` (ATS discovery), `analytics.html`

### AI Services

Provider-based architecture with routing in `backend/services/ai_service.py`:
- **OpenAI**: `openai_service.py` - Models: `gpt-4o-mini` (default), `gpt-4o`, `gpt-4-turbo`
- **Anthropic**: `anthropic_service.py` - Models: `claude-3-5-sonnet-20241022` (default), `claude-3-5-haiku`, `claude-3-opus`

Configuration stored in `AppSetting` table:
- `default_ai_provider`: "openai" or "anthropic"
- `ai_model`: Specific model override
- API keys: Environment vars (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) or database settings

### Scraper System

Located in `backend/scrapers/`, uses a mixin-based architecture with registry pattern.

**Base Classes** (`base.py`):
- `HTTPScraper` - For sites with JSON APIs (most common, ~80+ companies)
- `PlaywrightScraper` - For JavaScript-heavy sites (~20 companies)

**ATS Mixins** (defined in `custom/remaining_scrapers.py`, provide `scrape()` and `parse_job()`):
- `GreenhouseMixin` - boards-api.greenhouse.io
- `AshbyMixin` - api.ashbyhq.com
- `LeverMixin` - jobs.lever.co
- `SmartRecruitersMixin` - SmartRecruiters ATS
- `WorkdayHybridMixin` - Workday sites (requires Playwright, in `enterprise/workday_scrapers.py`)

**Adding a Greenhouse scraper** (most common pattern):
```python
from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry
from scrapers.custom.remaining_scrapers import GreenhouseMixin

@ScraperRegistry.register(category="custom")
class CompanyScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(
        company_slug="company-slug",
        company_name="Company Name",
        careers_url="https://company.com/careers",
        scraper_type=ScraperType.HTTP,
    )
    API_URL = "https://boards-api.greenhouse.io/v1/boards/company-slug/jobs"
```

**Scraper categories**: `big_tech/`, `enterprise/`, `finance/`, `other/`, `custom/`

### Background Tasks (Celery)

- **Broker**: Redis
- **Queues**: `scrapers_http` (10/min), `scrapers_browser` (5/min), `scrapers_orchestrator`, `maintenance`
- **Scheduled**: `scrape_all_companies` every 6 hours, cleanup tasks daily

## Auto-Apply Feature

**Supported**: Greenhouse, Lever, Workday
**NOT supported**: Ashby, iCIMS, Taleo, BrassRing, Jobvite, SmartRecruiters

Key endpoints:
- `POST /api/auto-apply/submit/{job_id}` - Submit application
- `GET /api/auto-apply/preflight/{job_id}` - Check availability

Implementation in `backend/services/auto_apply/` with ATS-specific classes.

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
When a scraper fails with 404/empty results, company may have migrated ATS:
- Anyscale: Greenhouse → Ashby
- Character AI: Greenhouse → Ashby

Check company careers page to identify new ATS, then update the scraper to use the appropriate mixin.
