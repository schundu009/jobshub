# JobTrails - Project Guide

A personal job application tracking system built with FastAPI backend and vanilla HTML/CSS/JS frontend.

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

## Common Issues

### Counts showing 0
- Check that `company_id` foreign key is set on Job records
- Verify the SQLAlchemy relationship is loading correctly
- Query the database directly: `SELECT company_id, COUNT(*) FROM jobs GROUP BY company_id`

### Empty tables
- Ensure data was properly migrated/imported
- Check for filtering issues in the API or frontend
