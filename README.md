# JobTrails

A personal job application tracking system to help organize your job search.

## Requirements

- Python 3.9 or higher

## Setup Instructions

### 1. Create virtual environment

```bash
cd /Users/chundu/jobportal
python3 -m venv venv
```

### 2. Activate virtual environment

**On macOS/Linux:**
```bash
source venv/bin/activate
```

**On Windows:**
```bash
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Start the backend server

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

### 5. Open the frontend

Option A: Open directly in browser
```
Open frontend/index.html in your web browser
```

Option B: Serve with Python (in a new terminal):
```bash
cd frontend
python3 -m http.server 3000
```
Then visit `http://localhost:3000`

## Project Structure

```
jobtrails/
├── backend/           # FastAPI backend
│   ├── main.py        # Application entry point
│   ├── database.py    # Database configuration
│   ├── models.py      # SQLAlchemy models
│   └── routes/        # API endpoints
├── frontend/          # HTML/CSS/JS frontend
│   ├── index.html     # Dashboard
│   ├── jobs.html      # Jobs list
│   ├── job_form.html  # Add/edit job
│   ├── job_detail.html# Job details
│   ├── companies.html # Companies list
│   ├── contacts.html  # Contacts list
│   ├── css/           # Stylesheets
│   └── js/            # JavaScript
├── data/              # SQLite database storage
├── requirements.txt   # Python dependencies
└── README.md          # This file
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/jobs | List all jobs |
| GET | /api/jobs/{id} | Get job details |
| POST | /api/jobs | Create a job |
| PUT | /api/jobs/{id} | Update a job |
| DELETE | /api/jobs/{id} | Delete a job |
| PATCH | /api/jobs/{id}/status | Update job status |
| GET | /api/companies | List all companies |
| GET | /api/companies/{id} | Get company details |
| POST | /api/companies | Create a company |
| PUT | /api/companies/{id} | Update a company |
| DELETE | /api/companies/{id} | Delete a company |
| GET | /api/contacts | List all contacts |
| GET | /api/contacts/{id} | Get contact details |
| POST | /api/contacts | Create a contact |
| PUT | /api/contacts/{id} | Update a contact |
| DELETE | /api/contacts/{id} | Delete a contact |
| GET | /api/interviews | List all interviews |
| GET | /api/interviews/upcoming | List upcoming interviews |
| POST | /api/interviews | Create an interview |
| PUT | /api/interviews/{id} | Update an interview |
| DELETE | /api/interviews/{id} | Delete an interview |
| GET | /api/notes/job/{job_id} | Get notes for a job |
| POST | /api/notes | Create a note |
| PUT | /api/notes/{id} | Update a note |
| DELETE | /api/notes/{id} | Delete a note |
| GET | /api/documents | List all documents |
| POST | /api/documents | Upload a document |
| DELETE | /api/documents/{id} | Delete a document |
| GET | /api/analytics/summary | Get dashboard summary |

## Features

- Track job applications with status (wishlist, applied, interviewing, offer, rejected, withdrawn)
- Manage companies and contacts
- Schedule and track interviews
- Add notes to jobs
- Upload documents (resumes, cover letters)
- Dashboard with statistics
- Search and filter capabilities
