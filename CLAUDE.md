# JobTrails - Project Guide

A personal job application tracking system built with FastAPI backend and vanilla HTML/CSS/JS frontend.

## CRITICAL: Always Deploy to Production

**This project runs on Railway (backend) and Vercel (frontend) - NOT localhost.**

After making code changes:
```bash
git add -A && git commit -m "Your message" && git push origin main
```

Railway and Vercel will auto-deploy from the `main` branch. Never test on localhost URLs - always verify on production:
- **Frontend**: https://cariara.vercel.app (or your Vercel URL)
- **Backend**: https://cariara-backend.up.railway.app
- **Admin**: https://cariara.vercel.app/admin/

## CRITICAL: Service Health Discipline

**ALWAYS verify services are running after ANY code change:**

```bash
# Check backend health
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/analytics/summary

# Check frontend health
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/

# Check uvicorn process
pgrep -fl "uvicorn"
```

- Backend with `--reload` auto-restarts on Python file changes
- If backend is down, restart: `cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000`
- If frontend is down, restart: `cd frontend && python3 -m http.server 3000`

**Never assume services are running. Always verify.**

## Quick Start

```bash
# Activate virtual environment
source venv/bin/activate

# Start backend server
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Serve frontend (separate terminal)
cd frontend && python3 -m http.server 3000
```

- Backend API: http://localhost:8000
- Frontend: http://localhost:3000

## Project Structure

```
jobportal/
├── backend/
│   ├── main.py           # FastAPI app entry point
│   ├── database.py       # SQLAlchemy setup (SQLite)
│   ├── models.py         # All SQLAlchemy models
│   ├── routes/           # API endpoints
│   │   ├── jobs.py       # Job CRUD + filtering
│   │   ├── companies.py  # Company CRUD
│   │   ├── contacts.py   # Contact CRUD
│   │   ├── interviews.py # Interview scheduling
│   │   ├── notes.py      # Job notes
│   │   ├── documents.py  # File uploads
│   │   ├── analytics.py  # Dashboard statistics
│   │   ├── ingest.py     # ATS job ingestion
│   │   ├── scrapers.py   # Custom scraper management
│   │   ├── ai.py         # AI-powered features
│   │   ├── users.py      # User & role profiles
│   │   └── settings.py   # App settings
│   ├── scrapers/         # Job board scrapers
│   ├── services/         # Business logic services
│   ├── tasks/            # Celery background tasks
│   └── utils/            # Helper utilities
├── frontend/
│   ├── index.html        # Dashboard
│   ├── jobs.html         # Jobs list with filtering
│   ├── job_form.html     # Add/edit job
│   ├── job_detail.html   # Job details view
│   ├── companies.html    # Companies management
│   ├── contacts.html     # Contacts management
│   ├── discover.html     # Job discovery from ATS
│   ├── analytics.html    # Charts & statistics
│   ├── settings.html     # App settings
│   ├── css/              # Stylesheets
│   └── js/               # Shared JavaScript
├── data/
│   └── jobtrails.db      # SQLite database
└── requirements.txt
```

## Database Models

### Core Models
- **Job** - Job postings with status tracking (wishlist, applied, interviewing, offer, rejected, withdrawn)
- **Company** - Company info, linked to jobs and contacts
- **Contact** - Networking contacts at companies
- **Interview** - Scheduled interviews with outcomes
- **Note** - Notes attached to jobs
- **Document** - Uploaded files (resumes, cover letters)

### Discovery Models
- **IngestionSource** - Tracks ATS career pages (Greenhouse, Lever, Ashby, Workday)
- **RoleProfile** - Job matching criteria (title patterns, keywords, seniority)
- **User** - User accounts with role preferences
- **JobRelevanceScore** - Cached relevance scores for job-user combinations

### Scraper Models
- **ScraperRun** - Scraper execution history
- **ScraperConfigDB** - Per-scraper configuration and health metrics

## Auto-Apply Feature

### Supported ATS Types
Auto-apply only works with these ATS platforms:
- **Greenhouse** (boards.greenhouse.io)
- **Lever** (jobs.lever.co)
- **Workday** (myworkdayjobs.com)

**NOT supported**: Ashby, iCIMS, Taleo, BrassRing, Jobvite, SmartRecruiters

For unsupported ATS types, the job detail page shows a "Apply Manually" button instead.

### Auto-Apply Endpoints
| Endpoint | Purpose |
|----------|---------|
| `/api/auto-apply/preflight/{job_id}` | Check if auto-apply is available |
| `/api/auto-apply/submit/{job_id}` | Submit application (immediate or queued) |
| `/api/auto-apply/submissions` | List user's application submissions |
| `/api/auto-apply/config` | Get/update auto-apply settings |

### Submit Options
- `process_immediately: true` - Apply now using browser automation
- `process_immediately: false` - Queue for Celery worker (requires Worker service)

## Key API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/api/jobs` | Job CRUD operations |
| `/api/companies` | Company management |
| `/api/contacts` | Contact management |
| `/api/interviews` | Interview scheduling |
| `/api/analytics/summary` | Dashboard stats (total_jobs, total_companies, status_counts) |
| `/api/analytics/by-company` | Jobs grouped by company with counts |
| `/api/ingest/sources` | Manage ATS ingestion sources |
| `/api/ingest/{ats_type}/{slug}` | Fetch jobs from ATS |
| `/api/scrapers` | Custom scraper management |

## Company Job Counts

Job counts for companies are calculated in two places:

1. **`/api/companies`** - Returns `job_count` per company via `len(company.jobs)`
2. **`/api/analytics/by-company`** - Groups jobs by company with status breakdown

The count relies on SQLAlchemy relationship `Company.jobs` being properly populated.

## Database Location

SQLite database: `data/jobtrails.db`

Configured in `backend/database.py`:
```python
DATABASE_URL = f"sqlite:///{os.path.join(DATA_DIR, 'jobtrails.db')}"
```

## Common Issues & Fixes

### Railway Deployment

#### OAuth redirect_uri_mismatch
- **Cause**: `BACKEND_URL` env var doesn't match actual Railway URL
- **Fix**: Ensure `BACKEND_URL=https://cariara-backend.up.railway.app` (not `cariara-backend-production`)

#### Jobs not saving to database (SSL errors)
- **Cause**: Railway internal PostgreSQL connections failing with SSL errors
- **Fix**: In `database.py`, add `sslmode=disable` for Railway internal connections:
```python
if 'railway.internal' in db_url and '?' not in db_url:
    db_url = f"{db_url}?sslmode=disable"
```

#### Worker not running / Scrapers not scheduling
- **Symptoms**: No new jobs since a specific date, Beat is running but Worker is down
- **Check**: Railway dashboard → Worker service logs
- **Fix**: Redeploy Worker service

#### Playwright browser not found
- **Error**: `chromium_headless_shell` not installed
- **Fix**: In `Dockerfile.worker`:
```dockerfile
RUN playwright install --with-deps chromium chromium-headless-shell
```

### Scraper Issues

#### Workday URL case sensitivity
- **Cause**: Site names like `External_Career` get lowercased to `external_career`
- **Fix**: In `ingestion_service.py`, extract site name from original URL before lowercasing

#### Company moved to different ATS
- **Symptoms**: 404 errors for specific companies
- **Common migrations**:
  - Anyscale: Greenhouse → Ashby (`https://api.ashbyhq.com/posting-api/job-board/anyscale`)
  - Character AI: Greenhouse → Ashby (`https://api.ashbyhq.com/posting-api/job-board/character`)
- **Fix**: Update scraper to use new ATS API

#### WorkdayPlaywrightMixin import error
- **Fix**: Add alias in `workday_scrapers.py`:
```python
WorkdayPlaywrightMixin = WorkdayHybridMixin
```

### Frontend Issues

#### "Loading job details..." stuck
- **Cause**: Using raw `fetch` instead of `apiRequest` helper
- **Fix**: Use `apiRequest('/jobs/${jobId}')` from `app.js` which handles auth & token refresh

#### Job description as single paragraph
- **Cause**: Plain text newlines ignored in HTML
- **Fix**: Add CSS `white-space: pre-line` to `.job-description-content`

#### Wrong job_detail.html routing
- **Cause**: Links pointing to `/admin/job_detail.html` instead of `/jobs/job_detail.html`
- **Fix**: Update href in discover.html to use correct path

#### Redis showing unhealthy on dashboard
- **Cause**: Using wrong health endpoint
- **Fix**: Use `/health/redis` endpoint instead of `/health`

### Database Issues

#### Counts showing 0
- Check that `company_id` foreign key is set on Job records
- Verify the SQLAlchemy relationship is loading correctly
- Query the database directly: `SELECT company_id, COUNT(*) FROM jobs GROUP BY company_id`

#### Empty tables
- Ensure data was properly migrated/imported
- Check for filtering issues in the API or frontend

#### Password reset on Railway
```python
import bcrypt
from sqlalchemy import create_engine, text
engine = create_engine("postgresql://postgres:PASSWORD@HOST:PORT/railway")
hashed = bcrypt.hashpw("newpassword".encode(), bcrypt.gensalt()).decode()
with engine.connect() as conn:
    conn.execute(text("UPDATE users SET hashed_password = :pwd WHERE email = :email"),
                 {"pwd": hashed, "email": "user@example.com"})
    conn.commit()
```

## Railway Services

| Service | Purpose | Key Files |
|---------|---------|-----------|
| Backend | FastAPI API server | `Dockerfile`, `main.py` |
| Worker | Celery task worker | `Dockerfile.worker`, `celery_app.py` |
| Beat | Celery scheduler | `Dockerfile.beat`, `celery_app.py` |
| Redis | Task queue broker | Railway managed |
| PostgreSQL | Database | Railway managed |

## Adding New Scrapers

### Greenhouse
```python
@ScraperRegistry.register(category="custom")
class CompanyScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="company", company_name="Company", ...)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/company/jobs"
```

### Ashby
```python
@ScraperRegistry.register(category="custom")
class CompanyScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="company", company_name="Company", ...)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/company"
```

### Workday
Add to `WORKDAY_COMPANIES` in `workday_scrapers.py`:
```python
("company", "Company Name", "company", "wd1", "External_Career_Site"),
```
