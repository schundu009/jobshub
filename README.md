# Cariara

A personal job application tracking system with AI-powered job discovery, ATS integration, and automated scraping capabilities.

## Features

**Core Tracking**
- Track job applications with status workflow (wishlist → applied → interviewing → offer/rejected/withdrawn)
- Manage companies and networking contacts
- Schedule interviews with outcome tracking
- Attach notes and documents to jobs

**Job Discovery**
- Ingest jobs from ATS platforms (Greenhouse, Lever, Ashby, Workday)
- AI-powered job relevance scoring based on role profiles
- Custom scraper support for any job board

**AI Features**
- Resume parsing and analysis
- Cover letter generation
- Job description analysis
- Role matching and recommendations

**Analytics**
- Dashboard with application statistics
- Status breakdown and trends
- Company-level insights

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI, Python 3.9+ |
| Database | SQLite (dev) / PostgreSQL (prod) |
| ORM | SQLAlchemy 2.0 |
| Task Queue | Celery + Redis |
| Auth | JWT, OAuth 2.0 (Google, GitHub, LinkedIn) |
| Scraping | Playwright, BeautifulSoup4 |
| AI | OpenAI API |
| Frontend | Vanilla HTML/CSS/JavaScript |

## Quick Start

### Prerequisites

- Python 3.9+
- Redis (optional, for background tasks)

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd Cariara

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (for scraping)
playwright install chromium
```

### Running the Application

**Start the backend:**
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

**Start the frontend (separate terminal):**
```bash
cd frontend && python3 -m http.server 3000
```

**Access the application:**
- Frontend: http://localhost:3000
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Optional: Background Tasks

For scraper scheduling and async processing:

```bash
# Start Redis
redis-server

# Start Celery worker
celery -A backend.celery_app worker --loglevel=info

# Start Celery beat (scheduler)
celery -A backend.celery_app beat --loglevel=info
```

## Project Structure

```
Cariara/
├── backend/
│   ├── main.py              # FastAPI application entry point
│   ├── database.py          # SQLAlchemy database configuration
│   ├── models.py            # Database models
│   ├── config.py            # Environment configuration
│   ├── celery_app.py        # Celery task queue setup
│   ├── routes/              # API endpoints
│   │   ├── jobs.py          # Job CRUD + filtering
│   │   ├── companies.py     # Company management
│   │   ├── contacts.py      # Contact management
│   │   ├── interviews.py    # Interview scheduling
│   │   ├── notes.py         # Job notes
│   │   ├── documents.py     # File uploads
│   │   ├── analytics.py     # Dashboard statistics
│   │   ├── ingest.py        # ATS job ingestion
│   │   ├── scrapers.py      # Custom scraper management
│   │   ├── ai.py            # AI-powered features
│   │   ├── users.py         # User management
│   │   ├── auth.py          # Authentication
│   │   └── settings.py      # App settings
│   ├── services/            # Business logic
│   │   ├── openai_service.py
│   │   ├── ingestion_service.py
│   │   ├── relevance_service.py
│   │   └── scraper_service.py
│   ├── scrapers/            # Job board scrapers
│   ├── tasks/               # Celery background tasks
│   └── schemas/             # Pydantic schemas
├── frontend/
│   ├── index.html           # Main dashboard
│   ├── jobs.html            # Jobs list with filtering
│   ├── job_form.html        # Add/edit job
│   ├── job_detail.html      # Job details view
│   ├── companies.html       # Companies management
│   ├── contacts.html        # Contacts management
│   ├── discover.html        # Job discovery from ATS
│   ├── analytics.html       # Charts & statistics
│   ├── settings.html        # App settings
│   ├── css/                 # Stylesheets
│   └── js/                  # Shared JavaScript
├── data/
│   └── Cariara.db         # SQLite database
└── requirements.txt
```

## API Reference

### Jobs

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/jobs` | List jobs (with filtering) |
| GET | `/api/jobs/{id}` | Get job details |
| POST | `/api/jobs` | Create a job |
| PUT | `/api/jobs/{id}` | Update a job |
| DELETE | `/api/jobs/{id}` | Delete a job |
| PATCH | `/api/jobs/{id}/status` | Update job status |

### Companies

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/companies` | List all companies |
| GET | `/api/companies/{id}` | Get company details |
| POST | `/api/companies` | Create a company |
| PUT | `/api/companies/{id}` | Update a company |
| DELETE | `/api/companies/{id}` | Delete a company |

### Contacts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/contacts` | List all contacts |
| GET | `/api/contacts/{id}` | Get contact details |
| POST | `/api/contacts` | Create a contact |
| PUT | `/api/contacts/{id}` | Update a contact |
| DELETE | `/api/contacts/{id}` | Delete a contact |

### Interviews

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/interviews` | List all interviews |
| GET | `/api/interviews/upcoming` | List upcoming interviews |
| POST | `/api/interviews` | Create an interview |
| PUT | `/api/interviews/{id}` | Update an interview |
| DELETE | `/api/interviews/{id}` | Delete an interview |

### Documents

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/documents` | List all documents |
| POST | `/api/documents` | Upload a document |
| DELETE | `/api/documents/{id}` | Delete a document |

### Job Discovery

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/ingest/sources` | List ingestion sources |
| POST | `/api/ingest/sources` | Add ATS source |
| GET | `/api/ingest/{ats_type}/{slug}` | Fetch jobs from ATS |
| POST | `/api/ingest/run/{source_id}` | Run ingestion for source |

### Analytics

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/analytics/summary` | Dashboard summary stats |
| GET | `/api/analytics/by-company` | Jobs grouped by company |
| GET | `/api/analytics/by-status` | Jobs grouped by status |

### AI Features

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/ai/parse-resume` | Parse resume content |
| POST | `/api/ai/generate-cover-letter` | Generate cover letter |
| POST | `/api/ai/analyze-job` | Analyze job description |
| POST | `/api/ai/match-score` | Calculate job match score |

## Environment Variables

Create a `.env` file in the project root:

```env
# Database (optional, defaults to SQLite)
DATABASE_URL=postgresql://user:pass@localhost/Cariara

# Redis (optional, for background tasks)
REDIS_URL=redis://localhost:6379/0

# OpenAI (required for AI features)
OPENAI_API_KEY=sk-...

# OAuth (optional)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...

# Security
SECRET_KEY=your-secret-key-here
```

## Database Models

### Core Models
- **Job** - Job postings with status, salary, location, description
- **Company** - Company information linked to jobs
- **Contact** - Networking contacts at companies
- **Interview** - Scheduled interviews with outcomes
- **Note** - Notes attached to jobs
- **Document** - Uploaded files (resumes, cover letters)

### Discovery Models
- **IngestionSource** - ATS career page configurations
- **RoleProfile** - Job matching criteria (titles, keywords, seniority)
- **User** - User accounts with preferences
- **JobRelevanceScore** - Cached relevance scores

### Scraper Models
- **ScraperRun** - Scraper execution history
- **ScraperConfigDB** - Scraper configuration and health

## Job Status Workflow

```
wishlist → applied → interviewing → offer
                  ↘               ↘ rejected
                   → withdrawn
```

## Development

### Running Tests

```bash
pytest
```

### Database Migrations

```bash
# Create migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head
```

### Code Style

The project uses standard Python conventions. Format with:

```bash
black backend/
isort backend/
```

## Troubleshooting

### Backend won't start
```bash
# Check if port is in use
lsof -i :8000

# Verify dependencies
pip install -r requirements.txt
```

### Database issues
```bash
# Reset database
rm data/Cariara.db
# Restart backend to recreate tables
```

### Scraper issues
```bash
# Reinstall Playwright browsers
playwright install chromium
```

## License

MIT License
