# JobTrails Enhancement Prompt for Claude CLI

Use this prompt with Claude CLI to systematically improve the application.

---

## Prompt

```
You are enhancing JobTrails, a personal job application tracking system built with FastAPI (backend) and vanilla HTML/CSS/JS (frontend). The codebase is in the current directory.

## Project Context
- Backend: FastAPI + SQLAlchemy + SQLite
- Frontend: Vanilla HTML/CSS/JS + AG Grid
- Background tasks: Celery + Redis
- Existing features: Job tracking, company/contact management, ATS ingestion, basic analytics

## Enhancement Areas

### 1. FRONTEND IMPROVEMENTS

**UI/UX Modernization:**
- Add dark mode toggle with localStorage persistence
- Implement a unified notification/toast system for user feedback
- Add keyboard shortcuts (Ctrl+N for new job, Ctrl+S to save, Escape to close modals)
- Create a global search bar (Cmd/Ctrl+K) to search jobs, companies, contacts
- Add drag-and-drop Kanban board view for job status management
- Improve mobile responsiveness across all pages

**Data Visualization:**
- Add interactive charts to analytics page (application funnel, timeline view, response rate trends)
- Create a calendar view showing interviews and application deadlines
- Add a salary range visualization/comparison tool

**Productivity Features:**
- Implement bulk actions (select multiple jobs, bulk status update, bulk delete)
- Add inline editing for job table cells
- Create job templates for quick entry of similar positions
- Add browser tab badge showing pending action counts

### 2. BACKEND IMPROVEMENTS

**API Enhancements:**
- Add API versioning (v1 prefix) for future compatibility
- Implement comprehensive request validation with detailed error messages
- Add pagination metadata (total_count, page, per_page, has_next) to all list endpoints
- Create a unified error response format with error codes
- Add request/response logging middleware with correlation IDs

**Performance & Caching:**
- Implement Redis caching for frequently accessed data (analytics summary, company list)
- Add database query optimization (eager loading, query batching)
- Implement rate limiting per endpoint category
- Add response compression (gzip)

**Data Management:**
- Create full data export endpoint (JSON/CSV) for backup
- Add data import endpoint with validation and conflict resolution
- Implement soft delete with restore capability
- Add audit logging for all data changes

### 3. ADVANCED CAPABILITIES

**AI-Powered Features:**
- Resume parser: Extract skills, experience from uploaded resumes
- Job-resume matcher: Score how well a resume matches a job description
- Cover letter generator: Generate tailored cover letters based on job + resume
- Interview question predictor: Suggest likely questions based on job description
- Salary estimator: Estimate salary range based on title, location, company size
- Application follow-up suggester: Recommend when and how to follow up

**Integrations:**
- Email integration: Track application emails, auto-detect responses
- Calendar sync: Sync interviews to Google Calendar/Outlook
- LinkedIn integration: Import job postings, company data
- Webhook system: Allow external services to subscribe to events (new job, status change)

**Smart Automation:**
- Auto-categorize jobs by industry/function based on description
- Detect duplicate job postings across sources
- Auto-archive stale applications (no activity for X days)
- Smart reminders: Interview prep reminders, follow-up reminders

**Analytics & Insights:**
- Application success rate by company size, industry, source
- Time-to-response analytics per company
- Skills gap analysis: Compare your skills vs job requirements
- Market insights: Trending skills, salary trends in your field
- Personalized recommendations: Best times to apply, companies to target

### 4. INFRASTRUCTURE

**Monitoring & Reliability:**
- Add health check endpoints with dependency status
- Implement structured logging with log levels
- Add performance metrics (response times, error rates)
- Create database backup/restore utilities

**Security:**
- Add CSRF protection for state-changing operations
- Implement API key rotation mechanism
- Add input sanitization for all user inputs
- Create security audit endpoint for admins

## Implementation Instructions

1. Start by reading existing code to understand patterns and conventions
2. Maintain backward compatibility - don't break existing functionality
3. Write clean, well-documented code following existing style
4. Add appropriate error handling and validation
5. Update CLAUDE.md if adding new features or endpoints
6. Test changes before committing

## Priority Order

Implement in this order for maximum impact:
1. Dark mode + notification system (quick wins, high visibility)
2. Global search + keyboard shortcuts (productivity boost)
3. AI job-resume matcher (differentiating feature)
4. Kanban board view (visual workflow improvement)
5. Data export/import (data safety)
6. Calendar integration (practical utility)
7. Advanced analytics (insights)

## Questions to Ask

Before implementing, clarify:
- Which specific feature should I implement first?
- Should I use any specific libraries (e.g., Chart.js for visualization)?
- What's the preferred approach for state management in the frontend?
- Should AI features use OpenAI API or allow multiple providers?

Begin by analyzing the current codebase structure and asking which enhancement area to prioritize.
```

---

## Quick-Start Commands

```bash
# Run with the full prompt
claude "$(cat ENHANCEMENT_PROMPT.md)"

# Or run specific sections
claude "Implement dark mode toggle for JobTrails frontend. Read the existing CSS and HTML files first, then add a theme switcher that persists to localStorage."

claude "Add a Kanban board view to the jobs page. Create a drag-and-drop interface where columns represent job statuses (wishlist, applied, interviewing, offer, rejected). Use the existing /api/jobs endpoints."

claude "Create an AI-powered job-resume matching feature. Add a new endpoint POST /api/ai/match-resume that accepts a job_id and resume text, then returns a compatibility score with detailed breakdown."

claude "Add comprehensive data export. Create GET /api/export endpoint that returns all user data (jobs, companies, contacts, interviews, notes) as JSON with optional CSV format."
```

---

## Feature-Specific Prompts

### Dark Mode
```
Add dark mode to JobTrails frontend:
1. Create CSS variables for colors in a :root and [data-theme="dark"] selector
2. Add a toggle button in the header/navbar
3. Persist preference to localStorage
4. Respect system preference (prefers-color-scheme) as default
5. Apply to all existing pages consistently
```

### Global Search
```
Implement global search (Cmd/Ctrl+K) for JobTrails:
1. Create a modal search interface that appears on keyboard shortcut
2. Search across jobs (title, company, description), companies (name), contacts (name, email)
3. Show categorized results with keyboard navigation
4. Navigate to selected item on Enter
5. Use debounced API calls or client-side filtering
```

### Kanban Board
```
Create a Kanban board view for job tracking:
1. Add a view toggle (table/kanban) to jobs page
2. Columns: Wishlist, Applied, Interviewing, Offer, Rejected, Withdrawn
3. Cards show: Job title, company, days in status
4. Drag-and-drop to change status (update via API)
5. Show count per column
6. Optional: Add color coding by priority or deadline
```

### AI Resume Matcher
```
Build AI-powered resume-job matching:
1. New endpoint: POST /api/ai/match
   - Input: job_id (or job description text) + resume_text
   - Output: score (0-100), matched_skills[], missing_skills[], suggestions[]
2. Frontend: Add "Check Match" button on job detail page
3. Display results in a visual format (progress bar, skill chips)
4. Cache results in JobRelevanceScore table
5. Use OpenAI API (gpt-4) for analysis
```

### Interview Calendar
```
Add interview calendar integration:
1. New endpoint: GET /api/interviews/ical - Returns iCal format
2. New endpoint: POST /api/integrations/google-calendar - OAuth flow
3. Frontend: Add "Add to Calendar" button on interview cards
4. Generate .ics file download as fallback
5. Include: Interview time, company, job title, location/link, notes
```
