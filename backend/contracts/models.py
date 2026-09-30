"""contract_jobs: contract / C2H / temp / freelance roles, separate from jobs."""
from sqlalchemy import (
    JSON, Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base
# ContractJob.company points at models.Company; importing it here keeps the
# mapper resolvable in processes that load only the contracts package
# (maintenance scripts, a worker running only contract tasks).
import models  # noqa: F401,E402

SOURCE_TYPES = ("staffing", "company_board", "aggregator")


class ContractJob(Base):
    __tablename__ = "contract_jobs"
    __table_args__ = (
        UniqueConstraint("source", "external_job_id", name="uq_contract_jobs_source_external"),
        Index("ix_contract_jobs_active_posted", "is_active", "effective_posted_at"),
        Index("ix_contract_jobs_active_type", "is_active", "employment_type"),
        Index("ix_contract_jobs_country_codes", "country_codes"),
        Index("ix_contract_jobs_source_active", "source", "is_active"),
    )

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(100), nullable=False)  # scraper slug
    source_type = Column(String(20), nullable=False, default="staffing")  # staffing | company_board | aggregator
    agency_name = Column(String(255), nullable=True)  # staffing agency that posted it
    end_client = Column(String(255), nullable=True)  # the client, when the agency names it
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)  # company-board roles

    title = Column(String(500), nullable=False)
    location = Column(String(500), nullable=True)
    country_codes = Column(String(200), nullable=True)  # ",US,GB," (services.job_location); NULL = unknown
    job_url = Column(Text, nullable=True)
    external_job_id = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    posted_date = Column(DateTime, nullable=True)
    first_seen_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    effective_posted_at = Column(DateTime, nullable=True)  # earlier of posted_date / first_seen_at
    is_active = Column(Boolean, default=True, nullable=False)

    employment_type = Column(String(20), nullable=False, default="contract")  # contract | contract_to_hire | temporary | freelance
    tax_terms = Column(JSON, nullable=True)  # subset of ["w2", "c2c", "1099"]
    pay_rate_min = Column(Float, nullable=True)
    pay_rate_max = Column(Float, nullable=True)
    pay_period = Column(String(10), nullable=True)  # hour | day | week | month | year
    hourly_rate_min = Column(Float, nullable=True)  # pay normalized to hourly (day/8, week/40, month/173.33, year/2080)
    hourly_rate_max = Column(Float, nullable=True)
    contract_duration_months = Column(Integer, nullable=True)
    visa_terms = Column(JSON, nullable=True)
    skills = Column(JSON, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    company = relationship("Company")
