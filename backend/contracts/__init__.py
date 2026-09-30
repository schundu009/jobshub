"""
Contract roles (W2 / C2C / 1099 / contract-to-hire), kept separate from the
full-time jobs pipeline: own table (contract_jobs), classifier, save service,
API (/api/contracts), Celery tasks (queue "contracts") and staffing scrapers.

The only coupling with the full-time pipeline: services.scraper_service routes
postings that contracts.classifier.detect_employment_type() calls contract
into contracts.service.save_contract_jobs(source_type="company_board").
"""
