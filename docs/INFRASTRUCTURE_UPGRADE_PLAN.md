# JobTrails Infrastructure Upgrade Plan

**Target Scale:** 50,000 users
**Deployment:** Local (PostgreSQL + Redis) → Cloud-ready
**Date:** January 2026

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Current vs Target Architecture](#current-vs-target-architecture)
3. [Phased Implementation Roadmap](#phased-implementation-roadmap)
4. [Detailed Phase Breakdown](#detailed-phase-breakdown)
5. [Database Migration Strategy](#database-migration-strategy)
6. [Security & Authentication](#security--authentication)
7. [Performance Considerations](#performance-considerations)
8. [Testing Strategy](#testing-strategy)
9. [Rollback Procedures](#rollback-procedures)

---

## Architecture Overview

### Current Architecture (Single User)

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENT LAYER                             │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              Vanilla HTML/CSS/JS Frontend                    │ │
│  │                   (localhost:3000)                           │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ HTTP
┌─────────────────────────────────────────────────────────────────┐
│                         API LAYER                                │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                  FastAPI Application                         │ │
│  │                   (localhost:8000)                           │ │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐            │ │
│  │  │  Jobs   │ │Companies│ │Contacts │ │Analytics│            │ │
│  │  │ Routes  │ │ Routes  │ │ Routes  │ │ Routes  │            │ │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘            │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ SQLAlchemy
┌─────────────────────────────────────────────────────────────────┐
│                        DATA LAYER                                │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    SQLite Database                           │ │
│  │                  (data/jobtrails.db)                         │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Target Architecture (50K Users)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                        │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │                    Static Frontend (HTML/CSS/JS)                             │ │
│  │                         (nginx :80/443)                                      │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼ HTTPS
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              GATEWAY LAYER                                       │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │                         nginx / Load Balancer                                │ │
│  │              (SSL Termination, Rate Limiting, Routing)                       │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                               API LAYER                                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐               │
│  │  FastAPI Node 1  │  │  FastAPI Node 2  │  │  FastAPI Node N  │               │
│  │    (uvicorn)     │  │    (uvicorn)     │  │    (uvicorn)     │               │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘               │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │                           Shared Components                                  │ │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐               │ │
│  │  │    Auth    │ │   Rate     │ │  Request   │ │   CORS     │               │ │
│  │  │ Middleware │ │  Limiter   │ │ Validator  │ │ Middleware │               │ │
│  │  └────────────┘ └────────────┘ └────────────┘ └────────────┘               │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
           │                    │                           │
           │                    │                           │
           ▼                    ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CACHE LAYER                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │                              Redis                                           │ │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐               │ │
│  │  │  Sessions  │ │   Cache    │ │   Rate     │ │   Celery   │               │ │
│  │  │  (JWT)     │ │  (Query)   │ │  Limits    │ │   Broker   │               │ │
│  │  └────────────┘ └────────────┘ └────────────┘ └────────────┘               │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       │
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            WORKER LAYER                                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐               │
│  │  Celery Worker 1 │  │  Celery Worker 2 │  │  Celery Beat     │               │
│  │  (Scraping)      │  │  (Notifications) │  │  (Scheduler)     │               │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘               │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              DATA LAYER                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │                           PostgreSQL                                         │ │
│  │  ┌────────────────────────────────────────────────────────────────────────┐ │ │
│  │  │                         Primary Database                                │ │ │
│  │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │ │ │
│  │  │  │  users   │ │   jobs   │ │companies │ │interviews│ │ relevance│     │ │ │
│  │  │  │          │ │          │ │          │ │          │ │  scores  │     │ │ │
│  │  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘     │ │ │
│  │  └────────────────────────────────────────────────────────────────────────┘ │ │
│  │                                                                              │ │
│  │  ┌────────────────────────────────────────────────────────────────────────┐ │ │
│  │  │                      PgBouncer (Connection Pool)                        │ │ │
│  │  └────────────────────────────────────────────────────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │                         File Storage (Local → S3)                            │ │
│  │                        /data/uploads → Object Storage                        │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Current vs Target Architecture

| Component | Current | Target | Priority |
|-----------|---------|--------|----------|
| Database | SQLite | PostgreSQL + PgBouncer | P0 |
| Authentication | None | JWT + Refresh Tokens | P0 |
| Session Management | None | Redis-backed sessions | P0 |
| Caching | None | Redis query cache | P1 |
| Rate Limiting | None | Redis-based per-user | P1 |
| Background Jobs | Celery (configured) | Celery + Redis broker | P1 |
| File Storage | Local filesystem | Local → Cloud-ready abstraction | P2 |
| Load Balancing | Single instance | nginx + multiple workers | P2 |
| Monitoring | Basic logging | Structured logging + metrics | P2 |
| Search | SQLite LIKE | PostgreSQL Full-Text → Elasticsearch | P3 |

---

## Phased Implementation Roadmap

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           IMPLEMENTATION TIMELINE                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  PHASE 1: Foundation                                                             │
│  ══════════════════                                                              │
│  ├── PostgreSQL Migration                                                        │
│  ├── Environment Configuration                                                   │
│  ├── Database Connection Pooling                                                 │
│  └── Data Migration Scripts                                                      │
│                                                                                  │
│  PHASE 2: Security                                                               │
│  ═════════════════                                                               │
│  ├── User Authentication (JWT)                                                   │
│  ├── Password Hashing (bcrypt)                                                   │
│  ├── Role-Based Access Control                                                   │
│  ├── Multi-tenancy (User Data Isolation)                                         │
│  └── API Security Hardening                                                      │
│                                                                                  │
│  PHASE 3: Performance                                                            │
│  ════════════════════                                                            │
│  ├── Redis Integration                                                           │
│  ├── Session Management                                                          │
│  ├── Query Caching                                                               │
│  ├── Rate Limiting                                                               │
│  └── Background Job Optimization                                                 │
│                                                                                  │
│  PHASE 4: Scale                                                                  │
│  ══════════════                                                                  │
│  ├── Multi-Worker Setup                                                          │
│  ├── nginx Configuration                                                         │
│  ├── Health Checks & Monitoring                                                  │
│  └── File Storage Abstraction                                                    │
│                                                                                  │
│  PHASE 5: Production Readiness                                                   │
│  ════════════════════════════                                                    │
│  ├── Load Testing (50K simulation)                                               │
│  ├── Security Audit                                                              │
│  ├── Documentation                                                               │
│  └── Cloud Migration Prep                                                        │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Detailed Phase Breakdown

### Phase 1: Foundation (PostgreSQL Migration)

**Objective:** Replace SQLite with PostgreSQL for multi-user concurrency support.

#### Tasks

| # | Task | Description | Dependencies |
|---|------|-------------|--------------|
| 1.1 | Environment config | Add `.env` support with pydantic-settings | None |
| 1.2 | PostgreSQL driver | Add `psycopg2-binary` and `asyncpg` | 1.1 |
| 1.3 | Update database.py | Configurable DB URL, connection pooling | 1.2 |
| 1.4 | Alembic setup | Database migrations framework | 1.3 |
| 1.5 | Initial migration | Generate schema from models | 1.4 |
| 1.6 | Data migration script | SQLite → PostgreSQL data transfer | 1.5 |
| 1.7 | UUID primary keys | Migrate from integer to UUID PKs | 1.6 |
| 1.8 | Index optimization | Add indexes for common queries | 1.7 |

#### File Changes

```
backend/
├── .env.example          # NEW: Environment template
├── config.py             # UPDATE: pydantic-settings
├── database.py           # UPDATE: PostgreSQL support
├── alembic.ini           # NEW: Alembic config
├── alembic/              # NEW: Migrations directory
│   ├── env.py
│   └── versions/
└── scripts/
    └── migrate_sqlite_to_postgres.py  # NEW: Data migration
```

#### Database Schema Changes

```sql
-- Primary key migration (Phase 1.7)
-- Before: id INTEGER PRIMARY KEY
-- After:  id UUID PRIMARY KEY DEFAULT gen_random_uuid()

-- Index additions (Phase 1.8)
CREATE INDEX idx_jobs_user_id ON jobs(user_id);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_company_id ON jobs(company_id);
CREATE INDEX idx_jobs_created_at ON jobs(created_at DESC);
CREATE INDEX idx_relevance_scores_user_job ON job_relevance_scores(user_id, job_id);
```

---

### Phase 2: Security (Authentication)

**Objective:** Add secure user authentication and multi-tenancy.

#### Tasks

| # | Task | Description | Dependencies |
|---|------|-------------|--------------|
| 2.1 | User model enhancement | Add password_hash, email_verified, etc. | Phase 1 |
| 2.2 | Password hashing | bcrypt integration | 2.1 |
| 2.3 | JWT implementation | Access + refresh token system | 2.2 |
| 2.4 | Auth routes | /auth/register, /login, /refresh, /logout | 2.3 |
| 2.5 | Auth middleware | Protect routes, inject current_user | 2.4 |
| 2.6 | Multi-tenancy | Add user_id FK to all user-owned tables | 2.5 |
| 2.7 | Data isolation | Filter all queries by current user | 2.6 |
| 2.8 | RBAC foundation | Admin vs regular user roles | 2.7 |
| 2.9 | Password reset | Email-based password reset flow | 2.8 |
| 2.10 | Frontend auth | Login/register pages, token handling | 2.9 |

#### Authentication Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           AUTHENTICATION FLOW                                    │
└─────────────────────────────────────────────────────────────────────────────────┘

  REGISTRATION                          LOGIN
  ════════════                          ═════

  Client                 Server         Client                 Server
    │                      │              │                      │
    │  POST /auth/register │              │  POST /auth/login    │
    │  {email, password,   │              │  {email, password}   │
    │   name}              │              │                      │
    │─────────────────────►│              │─────────────────────►│
    │                      │              │                      │
    │                      │ Validate     │                      │ Verify
    │                      │ Hash pwd     │                      │ password
    │                      │ Create user  │                      │
    │                      │              │                      │
    │  {access_token,      │              │  {access_token,      │
    │   refresh_token,     │              │   refresh_token,     │
    │   user}              │              │   user}              │
    │◄─────────────────────│              │◄─────────────────────│
    │                      │              │                      │


  TOKEN REFRESH                         PROTECTED REQUEST
  ═════════════                         ═════════════════

  Client                 Server         Client                 Server
    │                      │              │                      │
    │  POST /auth/refresh  │              │  GET /api/jobs       │
    │  {refresh_token}     │              │  Authorization:      │
    │                      │              │  Bearer <token>      │
    │─────────────────────►│              │─────────────────────►│
    │                      │              │                      │
    │                      │ Validate     │                      │ Validate
    │                      │ Issue new    │                      │ Extract user
    │                      │              │                      │ Filter by user
    │                      │              │                      │
    │  {access_token,      │              │  {jobs: [...]}       │
    │   refresh_token}     │              │  (user's jobs only)  │
    │◄─────────────────────│              │◄─────────────────────│
    │                      │              │                      │
```

#### JWT Token Structure

```python
# Access Token (short-lived: 15 min)
{
    "sub": "user_uuid",
    "email": "user@example.com",
    "role": "user",
    "exp": 1234567890,
    "iat": 1234567890,
    "type": "access"
}

# Refresh Token (long-lived: 7 days)
{
    "sub": "user_uuid",
    "exp": 1234567890,
    "iat": 1234567890,
    "type": "refresh",
    "jti": "unique_token_id"  # For revocation
}
```

#### File Changes

```
backend/
├── routes/
│   └── auth.py           # NEW: Auth endpoints
├── services/
│   ├── auth_service.py   # NEW: Auth business logic
│   └── token_service.py  # NEW: JWT handling
├── middleware/
│   └── auth.py           # NEW: Auth middleware
├── schemas/
│   └── auth.py           # NEW: Auth request/response schemas
└── utils/
    └── security.py       # NEW: Password hashing, etc.

frontend/
├── login.html            # NEW: Login page
├── register.html         # NEW: Registration page
└── js/
    └── auth.js           # NEW: Token management
```

#### Multi-Tenancy Schema Changes

```sql
-- Add user_id to all user-owned tables
ALTER TABLE jobs ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE companies ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE contacts ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE interviews ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE notes ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE documents ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE ingestion_sources ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE CASCADE;

-- Composite indexes for user-scoped queries
CREATE INDEX idx_jobs_user_status ON jobs(user_id, status);
CREATE INDEX idx_companies_user ON companies(user_id);
```

---

### Phase 3: Performance (Redis Integration)

**Objective:** Add caching, session management, and rate limiting.

#### Tasks

| # | Task | Description | Dependencies |
|---|------|-------------|--------------|
| 3.1 | Redis client setup | aioredis configuration | Phase 2 |
| 3.2 | Session storage | Store refresh tokens in Redis | 3.1 |
| 3.3 | Token blacklist | Logout invalidation | 3.2 |
| 3.4 | Query caching | Cache frequent reads (analytics, companies) | 3.3 |
| 3.5 | Cache invalidation | Invalidate on writes | 3.4 |
| 3.6 | Rate limiter | Per-user request limits | 3.5 |
| 3.7 | Celery broker | Switch to Redis broker | 3.6 |
| 3.8 | Job deduplication | Prevent duplicate scraper runs | 3.7 |

#### Redis Data Structures

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                             REDIS SCHEMA                                         │
└─────────────────────────────────────────────────────────────────────────────────┘

  SESSIONS (Hash)                       CACHE (String with TTL)
  ═══════════════                       ═══════════════════════

  Key: session:{user_id}                Key: cache:analytics:{user_id}
  ┌────────────────────────────┐        ┌────────────────────────────┐
  │ refresh_token: "..."       │        │ {                          │
  │ created_at: "timestamp"    │        │   "total_jobs": 150,       │
  │ device: "Chrome/Mac"       │        │   "status_counts": {...},  │
  │ ip: "127.0.0.1"            │        │   "cached_at": "..."       │
  │                            │        │ }                          │
  └────────────────────────────┘        └────────────────────────────┘
  TTL: 7 days                           TTL: 5 minutes


  TOKEN BLACKLIST (Set)                 RATE LIMITS (Sorted Set)
  ═════════════════════                 ════════════════════════

  Key: blacklist:tokens                 Key: ratelimit:{user_id}:{window}
  ┌────────────────────────────┐        ┌────────────────────────────┐
  │ "jti_abc123"               │        │ Score: timestamp           │
  │ "jti_def456"               │        │ Member: request_id         │
  │ "jti_ghi789"               │        │                            │
  └────────────────────────────┘        └────────────────────────────┘
  TTL: Match token expiry               TTL: Window size (1 min)


  CELERY QUEUES                         LOCKS (String)
  ═════════════                         ══════════════

  Key: celery (List)                    Key: lock:scraper:{company_slug}
  ┌────────────────────────────┐        ┌────────────────────────────┐
  │ Task messages (FIFO)       │        │ "worker_id"                │
  └────────────────────────────┘        └────────────────────────────┘
                                        TTL: 5 minutes (auto-release)
```

#### Rate Limiting Strategy

```python
# Rate limits per endpoint category
RATE_LIMITS = {
    "auth": {
        "login": "5/minute",      # Prevent brute force
        "register": "3/hour",     # Prevent spam
        "refresh": "10/minute",
    },
    "api": {
        "read": "100/minute",     # GET requests
        "write": "30/minute",     # POST/PUT/DELETE
        "search": "20/minute",    # Search operations
    },
    "scraper": {
        "trigger": "5/hour",      # Manual scraper triggers
    }
}
```

---

### Phase 4: Scale (Multi-Worker & Load Balancing)

**Objective:** Enable horizontal scaling with multiple workers.

#### Tasks

| # | Task | Description | Dependencies |
|---|------|-------------|--------------|
| 4.1 | Gunicorn setup | Production WSGI server with workers | Phase 3 |
| 4.2 | nginx config | Reverse proxy and load balancing | 4.1 |
| 4.3 | Health endpoints | /health and /ready endpoints | 4.2 |
| 4.4 | Graceful shutdown | Handle SIGTERM properly | 4.3 |
| 4.5 | Static file serving | nginx serves frontend | 4.4 |
| 4.6 | File upload abstraction | Storage backend interface | 4.5 |
| 4.7 | Local file storage | Implement local storage backend | 4.6 |
| 4.8 | Docker setup | Containerize all services | 4.7 |
| 4.9 | Docker Compose | Local multi-service orchestration | 4.8 |

#### Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         LOCAL DEPLOYMENT TOPOLOGY                                │
└─────────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────┐
                              │   nginx :80     │
                              │   (gateway)     │
                              └────────┬────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              │                        │                        │
              ▼                        ▼                        ▼
    ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
    │  /api/* proxy   │      │  /static/*      │      │     / root      │
    │                 │      │  (frontend)     │      │   (frontend)    │
    └────────┬────────┘      └─────────────────┘      └─────────────────┘
             │
             ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                    Gunicorn (4 workers)                          │
    │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐        │
    │  │ Worker 1  │ │ Worker 2  │ │ Worker 3  │ │ Worker 4  │        │
    │  │ (uvicorn) │ │ (uvicorn) │ │ (uvicorn) │ │ (uvicorn) │        │
    │  └───────────┘ └───────────┘ └───────────┘ └───────────┘        │
    └─────────────────────────────────────────────────────────────────┘
             │                                           │
             ▼                                           ▼
    ┌─────────────────┐                        ┌─────────────────┐
    │   PostgreSQL    │                        │      Redis      │
    │    :5432        │                        │     :6379       │
    └─────────────────┘                        └─────────────────┘
```

#### Docker Compose Structure

```yaml
# docker-compose.yml structure
services:
  nginx:
    ports: ["80:80"]
    depends_on: [api, frontend]

  api:
    build: ./backend
    replicas: 4
    depends_on: [postgres, redis]
    environment:
      - DATABASE_URL
      - REDIS_URL

  celery-worker:
    build: ./backend
    command: celery worker
    replicas: 2
    depends_on: [postgres, redis]

  celery-beat:
    build: ./backend
    command: celery beat
    depends_on: [redis]

  frontend:
    build: ./frontend

  postgres:
    image: postgres:16
    volumes: [postgres_data:/var/lib/postgresql/data]

  redis:
    image: redis:7-alpine
    volumes: [redis_data:/data]
```

---

### Phase 5: Production Readiness

**Objective:** Validate system under load and prepare for cloud migration.

#### Tasks

| # | Task | Description | Dependencies |
|---|------|-------------|--------------|
| 5.1 | Load test setup | Locust test scenarios | Phase 4 |
| 5.2 | 50K user simulation | Concurrent user load testing | 5.1 |
| 5.3 | Performance tuning | Optimize based on results | 5.2 |
| 5.4 | Security audit | OWASP checklist review | 5.3 |
| 5.5 | Structured logging | JSON logs with request IDs | 5.4 |
| 5.6 | Metrics export | Prometheus metrics endpoint | 5.5 |
| 5.7 | API documentation | OpenAPI spec complete | 5.6 |
| 5.8 | Deployment docs | Local & cloud deployment guide | 5.7 |
| 5.9 | Cloud migration prep | Terraform/IaC templates | 5.8 |

#### Load Testing Scenarios

```python
# Locust test scenarios for 50K users

class JobTrailsUser(HttpUser):
    wait_time = between(1, 5)

    # User behavior weights (simulate real usage)
    @task(10)
    def view_dashboard(self):
        """Most common: view dashboard"""
        self.client.get("/api/analytics/summary")

    @task(8)
    def list_jobs(self):
        """Common: browse jobs"""
        self.client.get("/api/jobs?limit=20")

    @task(5)
    def view_job_detail(self):
        """Moderate: view specific job"""
        self.client.get(f"/api/jobs/{random_job_id}")

    @task(2)
    def create_job(self):
        """Less common: add new job"""
        self.client.post("/api/jobs", json={...})

    @task(1)
    def run_scraper(self):
        """Rare: trigger scraper"""
        self.client.post("/api/scrapers/greenhouse/run")
```

---

## Database Migration Strategy

### SQLite to PostgreSQL Migration

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         DATA MIGRATION WORKFLOW                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

  Step 1: Schema Migration              Step 2: Data Export
  ═════════════════════                 ═══════════════════

  ┌─────────────────────┐               ┌─────────────────────┐
  │  SQLite Schema      │               │  SQLite Data        │
  │  (models.py)        │               │  (jobtrails.db)     │
  └──────────┬──────────┘               └──────────┬──────────┘
             │                                     │
             ▼                                     ▼
  ┌─────────────────────┐               ┌─────────────────────┐
  │  Alembic generates  │               │  Export to JSON/CSV │
  │  initial migration  │               │  with ID mapping    │
  └──────────┬──────────┘               └──────────┬──────────┘
             │                                     │
             ▼                                     │
  ┌─────────────────────┐                          │
  │  PostgreSQL Schema  │                          │
  │  (empty tables)     │◄─────────────────────────┘
  └─────────────────────┘
                                        Step 3: Data Import
                                        ═══════════════════

                                        ┌─────────────────────┐
                                        │  Import with UUID   │
                                        │  generation         │
                                        └─────────────────────┘
```

### Migration Script Outline

```python
# scripts/migrate_sqlite_to_postgres.py

def migrate():
    # 1. Connect to both databases
    sqlite_conn = connect_sqlite()
    pg_conn = connect_postgres()

    # 2. Disable FK constraints temporarily
    pg_conn.execute("SET session_replication_role = 'replica'")

    # 3. Migrate tables in dependency order
    tables = [
        'role_profiles',  # No FKs
        'users',          # FK: role_profiles
        'companies',      # FK: users (after multi-tenancy)
        'jobs',           # FK: companies, users
        'contacts',       # FK: companies, users
        'interviews',     # FK: jobs
        'notes',          # FK: jobs
        'documents',      # FK: jobs
        'ingestion_sources',
        'job_relevance_scores',
        'scraper_runs',
        'scraper_configs',
    ]

    # 4. For each table:
    #    - Map old INT ids to new UUIDs
    #    - Transform data types (datetime, json)
    #    - Insert into PostgreSQL

    # 5. Re-enable constraints
    pg_conn.execute("SET session_replication_role = 'origin'")

    # 6. Verify counts match
    verify_migration()
```

---

## Security & Authentication

### Security Checklist

| Category | Item | Status |
|----------|------|--------|
| **Authentication** | JWT with short expiry | Phase 2 |
| | Refresh token rotation | Phase 2 |
| | Password hashing (bcrypt) | Phase 2 |
| | Account lockout after failures | Phase 2 |
| **Authorization** | User data isolation | Phase 2 |
| | Role-based access | Phase 2 |
| | API key for scrapers | Phase 3 |
| **Transport** | HTTPS only (production) | Phase 4 |
| | Secure cookie flags | Phase 2 |
| **Input Validation** | Request schema validation | Existing |
| | SQL injection prevention (ORM) | Existing |
| | XSS prevention | Phase 2 |
| **Rate Limiting** | Per-user limits | Phase 3 |
| | Auth endpoint protection | Phase 3 |
| **Headers** | CORS configuration | Phase 2 |
| | Security headers (CSP, etc.) | Phase 4 |

---

## Performance Considerations

### Database Query Optimization

```sql
-- Key indexes for 50K users with ~100 jobs each = 5M jobs

-- Most frequent query: User's jobs with status filter
CREATE INDEX idx_jobs_user_status_created
ON jobs(user_id, status, created_at DESC);

-- Dashboard analytics
CREATE INDEX idx_jobs_user_date_applied
ON jobs(user_id, date_applied)
WHERE date_applied IS NOT NULL;

-- Company lookup with job count
CREATE INDEX idx_jobs_company_user
ON jobs(company_id, user_id);

-- Full-text search on job titles/descriptions
CREATE INDEX idx_jobs_search
ON jobs USING gin(to_tsvector('english', title || ' ' || COALESCE(job_description, '')));
```

### Caching Strategy

| Data | Cache TTL | Invalidation |
|------|-----------|--------------|
| User session | 7 days | Logout, password change |
| Analytics summary | 5 min | Job create/update/delete |
| Company list | 10 min | Company create/update |
| Role profiles | 1 hour | Profile update |
| Job search results | 2 min | Job changes |

### Connection Pool Settings

```python
# For 50K users with ~10% concurrent = 5K connections
# With 4 API workers = 1,250 per worker

# PgBouncer config (recommended)
POOL_MODE = "transaction"
MAX_CLIENT_CONN = 5000
DEFAULT_POOL_SIZE = 100
MIN_POOL_SIZE = 10
RESERVE_POOL_SIZE = 25

# SQLAlchemy settings
SQLALCHEMY_POOL_SIZE = 20
SQLALCHEMY_MAX_OVERFLOW = 30
SQLALCHEMY_POOL_TIMEOUT = 30
SQLALCHEMY_POOL_RECYCLE = 1800
```

---

## Testing Strategy

### Test Categories

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              TEST PYRAMID                                        │
└─────────────────────────────────────────────────────────────────────────────────┘

                           ┌─────────────────┐
                           │    E2E Tests    │  ← Browser automation
                           │   (Playwright)  │     10% of tests
                           └────────┬────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │      Integration Tests        │  ← API + DB
                    │        (pytest + DB)          │     30% of tests
                    └───────────────┬───────────────┘
                                    │
        ┌───────────────────────────┴───────────────────────────┐
        │                    Unit Tests                          │  ← Fast, isolated
        │                (pytest, mocked DB)                     │     60% of tests
        └────────────────────────────────────────────────────────┘
```

### Test Additions per Phase

| Phase | Test Focus | Tools |
|-------|-----------|-------|
| 1 | PostgreSQL compatibility | pytest + test DB |
| 2 | Auth flows, token validation | pytest, JWT mocking |
| 3 | Cache behavior, rate limiting | Redis testcontainers |
| 4 | Multi-worker, load handling | Locust, pytest-benchmark |
| 5 | Full E2E, security | Playwright, OWASP ZAP |

---

## Rollback Procedures

### Phase 1 Rollback (PostgreSQL)

```bash
# If PostgreSQL migration fails:
# 1. Point DATABASE_URL back to SQLite
export DATABASE_URL="sqlite:///data/jobtrails.db"

# 2. Restart application
systemctl restart jobtrails
```

### Phase 2 Rollback (Auth)

```bash
# If auth causes issues:
# 1. Disable auth middleware temporarily
export AUTH_ENABLED=false

# 2. Or revert to pre-auth commit
git checkout phase1-complete
```

### Database Backup Strategy

```bash
# Before each phase:
pg_dump jobtrails > backup_phase_N_$(date +%Y%m%d).sql

# Keep SQLite backup until phase 3 complete:
cp data/jobtrails.db data/jobtrails_backup.db
```

---

## Summary: Deliverables per Phase

| Phase | Key Deliverables | Success Criteria |
|-------|-----------------|------------------|
| **1** | PostgreSQL running, data migrated | All existing functionality works |
| **2** | User auth, multi-tenancy | Users can register, login, see only their data |
| **3** | Redis caching, rate limiting | 50% faster reads, no abuse possible |
| **4** | Docker Compose, nginx | 4 workers handling traffic |
| **5** | Load tested, documented | 50K simulated users, <200ms p95 latency |

---

## Next Steps

1. **Verify Prerequisites:** Confirm PostgreSQL and Redis are running locally
2. **Start Phase 1:** Begin with environment configuration
3. **Incremental Progress:** Complete each phase before moving to next
4. **Testing:** Run test suite after each major change

Ready to begin implementation?
