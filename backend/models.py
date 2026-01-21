from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey, Boolean, Float, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

# Handle imports whether running from backend/ or project root
try:
    from database import Base
except ImportError:
    from database import Base


# ============== Role-Aware Discovery Models ==============

class RoleProfile(Base):
    """
    Defines a professional role with relevance scoring criteria.

    Role profiles are data-driven and define:
    - Allowed/preferred job titles (patterns)
    - Positive keywords (weighted by importance)
    - Negative keywords (for filtering/penalties)
    - Seniority preferences

    Profiles are reusable across multiple users.
    """
    __tablename__ = "role_profiles"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(50), unique=True, nullable=False, index=True)  # e.g., "devops", "backend"
    name = Column(String(100), nullable=False)  # e.g., "DevOps Engineer"
    description = Column(Text)  # Optional description of the role

    # Title matching patterns (JSON)
    # Format: {"strong_match": ["devops", "sre"], "weak_match": ["platform"], "exclude": ["frontend"]}
    title_patterns = Column(JSON, nullable=False, default=dict)

    # Keyword weights for description matching (JSON)
    # Format: {"high": ["kubernetes", "docker"], "medium": ["linux"], "low": ["automation"]}
    positive_keywords = Column(JSON, nullable=False, default=dict)

    # Keywords that reduce relevance score (JSON array)
    negative_keywords = Column(JSON, nullable=False, default=list)

    # Seniority preferences (JSON)
    # Format: {"preferred": ["senior", "staff"], "acceptable": ["mid"], "exclude": ["intern"]}
    seniority_config = Column(JSON, default=dict)

    # Scoring thresholds
    relevance_threshold = Column(Float, default=30.0)  # Minimum score to be considered relevant

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    users = relationship("User", back_populates="role_profile")


class User(Base):
    """
    User account with authentication and role-based job discovery preferences.

    Each user selects a role profile that determines which jobs
    are relevant to them. The same job may be relevant for one
    user and irrelevant for another based on their role.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)

    # Authentication fields
    password_hash = Column(String(255), nullable=True)  # Nullable for migration, required for new users
    is_email_verified = Column(Boolean, default=False)
    email_verification_token = Column(String(255), nullable=True)
    password_reset_token = Column(String(255), nullable=True)
    password_reset_expires = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)

    # Role (admin can manage all users, user is default)
    role = Column(String(20), default="user")  # "user", "admin"

    # Role-based discovery
    role_profile_id = Column(Integer, ForeignKey("role_profiles.id"))

    # User-specific customizations (JSON)
    # Can override role profile settings: {"extra_keywords": [], "blocked_companies": []}
    custom_preferences = Column(JSON, default=dict)

    # Preferred locations for filtering (JSON array)
    preferred_locations = Column(JSON, default=list)

    # Seniority preference override
    target_seniority = Column(String(50))  # "junior", "mid", "senior", "staff", "principal"

    # Salary preferences
    min_salary = Column(Integer)

    # Application Profile fields
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    preferred_name = Column(String(100), nullable=True)
    phone = Column(String(50), nullable=True)
    country = Column(String(50), nullable=True)

    # Address fields
    address_line1 = Column(String(255), nullable=True)
    address_line2 = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    postal_code = Column(String(20), nullable=True)
    address_country = Column(String(50), nullable=True)

    # Work authorization fields
    us_authorized = Column(String(20), nullable=True)  # yes, no
    requires_sponsorship = Column(String(20), nullable=True)  # yes, no
    willing_to_relocate = Column(String(20), nullable=True)  # yes, no, depends
    us_government_employee = Column(String(20), nullable=True)  # yes, no
    non_compete = Column(String(20), nullable=True)  # yes, no
    work_arrangement = Column(String(20), nullable=True)  # remote, hybrid, onsite, flexible

    # Social profiles
    linkedin_url = Column(String(500), nullable=True)
    github_url = Column(String(500), nullable=True)
    portfolio_url = Column(String(500), nullable=True)
    twitter_url = Column(String(500), nullable=True)

    # Professional summary
    referral_source = Column(String(50), nullable=True)
    bio = Column(Text, nullable=True)
    skills = Column(Text, nullable=True)

    # Demographics / EEO fields
    gender = Column(String(20), nullable=True)  # male, female, non_binary, other, decline
    ethnicity = Column(String(50), nullable=True)  # american_indian, asian, black, hispanic, pacific_islander, white, two_or_more, decline
    veteran_status = Column(String(30), nullable=True)  # not_veteran, veteran, protected_veteran, decline
    disability_status = Column(String(20), nullable=True)  # no, yes, decline

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    role_profile = relationship("RoleProfile", back_populates="users")
    relevance_scores = relationship("JobRelevanceScore", back_populates="user", cascade="all, delete-orphan")

    # Relationships for owned resources (multi-tenancy)
    jobs = relationship("Job", back_populates="owner", cascade="all, delete-orphan")
    companies = relationship("Company", back_populates="owner", cascade="all, delete-orphan")
    contacts = relationship("Contact", back_populates="owner", cascade="all, delete-orphan")
    documents = relationship("UserDocument", back_populates="owner", cascade="all, delete-orphan")


class UserDocument(Base):
    """
    User uploaded documents (resumes, cover letters, etc.)
    """
    __tablename__ = "user_documents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    document_type = Column(String(50), nullable=False)  # resume, cover_letter
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    owner = relationship("User", back_populates="documents")


class JobRelevanceScore(Base):
    """
    Cached relevance scores for job-user combinations.

    Pre-computed scores enable fast querying without real-time calculation.
    Scores are recomputed when:
    - New jobs are ingested
    - User's role profile changes
    - Role profile definition is updated

    This is an optimization - relevance can also be computed at query time.
    """
    __tablename__ = "job_relevance_scores"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Computed relevance
    relevance_score = Column(Float, nullable=False, index=True)  # 0-100 scale
    is_relevant = Column(Boolean, nullable=False, index=True)  # Score >= threshold

    # Score breakdown for explainability (JSON)
    # {"title_score": 40, "keyword_score": 35, "seniority_bonus": 10, "penalties": -5}
    score_breakdown = Column(JSON)

    # Tracking
    computed_at = Column(DateTime, server_default=func.now())
    role_profile_id = Column(Integer)  # Snapshot of which profile was used

    job = relationship("Job", back_populates="relevance_scores")
    user = relationship("User", back_populates="relevance_scores")


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    website = Column(String(500))
    industry = Column(String(255))
    size = Column(String(50))
    location = Column(String(255))
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

    owner = relationship("User", back_populates="companies")
    jobs = relationship("Job", back_populates="company")
    contacts = relationship("Contact", back_populates="company")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"))
    location = Column(String(255))
    salary_min = Column(Integer)
    salary_max = Column(Integer)
    job_url = Column(String(500))
    job_description = Column(Text)
    status = Column(String(50), default="wishlist")
    date_found = Column(Date)
    date_applied = Column(Date)
    excitement_level = Column(Integer, default=3)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Ingestion fields
    source = Column(String(50), default="manual")  # manual, greenhouse, lever
    external_job_id = Column(String(255))  # ID from the ATS
    is_active = Column(Boolean, default=True)  # False if job no longer exists in ATS
    posted_date = Column(DateTime)  # When the job was originally posted on the ATS
    department = Column(String(255))  # Department/team from ATS

    owner = relationship("User", back_populates="jobs")
    company = relationship("Company", back_populates="jobs")
    interviews = relationship("Interview", back_populates="job", cascade="all, delete-orphan")
    notes = relationship("Note", back_populates="job", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="job", cascade="all, delete-orphan")
    relevance_scores = relationship("JobRelevanceScore", back_populates="job", cascade="all, delete-orphan")


class IngestionSource(Base):
    """Tracks company career pages for automatic refresh."""
    __tablename__ = "ingestion_sources"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    ats_type = Column(String(50), nullable=False)  # greenhouse, lever, ashby, workday, etc.
    ats_company_slug = Column(String(255), nullable=False)  # e.g., "stripe" for Stripe's Greenhouse
    company_name = Column(String(255))  # Display name, can be set before first ingestion
    career_page_url = Column(String(500))
    last_checked_at = Column(DateTime)  # Last time we attempted to fetch jobs
    last_successful_at = Column(DateTime)  # Last time jobs were successfully fetched
    job_count = Column(Integer, default=0)  # Number of jobs found in last check
    is_active = Column(Boolean, default=True)  # False if company not found or disabled
    error_message = Column(String(500))  # Last error if any
    created_at = Column(DateTime, server_default=func.now())

    company = relationship("Company")


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255))
    phone = Column(String(50))
    linkedin_url = Column(String(500))
    company_id = Column(Integer, ForeignKey("companies.id"))
    role = Column(String(255))
    relationship_type = Column(String(50))
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

    owner = relationship("User", back_populates="contacts")
    company = relationship("Company", back_populates="contacts")


class Interview(Base):
    __tablename__ = "interviews"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    interview_date = Column(DateTime, nullable=False)
    interview_type = Column(String(50))
    interviewer_names = Column(String(500))
    location = Column(String(500))
    notes = Column(Text)
    outcome = Column(String(50), default="pending")
    created_at = Column(DateTime, server_default=func.now())

    job = relationship("Job", back_populates="interviews")


class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    content = Column(Text, nullable=False)
    note_type = Column(String(50), default="general")
    created_at = Column(DateTime, server_default=func.now())

    job = relationship("Job", back_populates="notes")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"))
    name = Column(String(255), nullable=False)
    doc_type = Column(String(50))
    file_path = Column(String(500))
    created_at = Column(DateTime, server_default=func.now())

    job = relationship("Job", back_populates="documents")


# ============== Custom Scraper Models ==============

class ScraperRun(Base):
    """
    Tracks scraper executions for monitoring and debugging.

    Each run records success/failure, timing, and job counts to help
    identify scrapers that need attention.
    """
    __tablename__ = "scraper_runs"

    id = Column(Integer, primary_key=True, index=True)
    company_slug = Column(String(100), nullable=False, index=True)

    # Status
    success = Column(Boolean, nullable=False, index=True)
    jobs_found = Column(Integer, default=0)
    jobs_new = Column(Integer, default=0)
    jobs_updated = Column(Integer, default=0)

    # Timing
    duration_seconds = Column(Float)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Pagination
    pages_scraped = Column(Integer, default=0)

    # Errors
    error_message = Column(Text)
    error_type = Column(String(50))  # timeout, rate_limited, blocked, parse_error, network_error

    # Metadata
    run_at = Column(DateTime, server_default=func.now(), index=True)
    celery_task_id = Column(String(100))  # For tracking async tasks


class ScraperConfigDB(Base):
    """
    Runtime configuration per scraper.

    Allows enabling/disabling scrapers and overriding settings without
    code changes. Also tracks health metrics for alerting.
    """
    __tablename__ = "scraper_configs"

    id = Column(Integer, primary_key=True, index=True)
    company_slug = Column(String(100), unique=True, nullable=False, index=True)

    # Status
    is_enabled = Column(Boolean, default=True, index=True)

    # Override settings (JSON)
    # Can override: rate_limit, max_retries, page_timeout, max_pages
    config_overrides = Column(JSON, default=dict)

    # Health tracking
    last_success_at = Column(DateTime)
    last_failure_at = Column(DateTime)
    consecutive_failures = Column(Integer, default=0)
    total_runs = Column(Integer, default=0)
    total_jobs_found = Column(Integer, default=0)

    # Schedule override
    schedule_cron = Column(String(100))  # Custom cron schedule, e.g., "0 */4 * * *"

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
