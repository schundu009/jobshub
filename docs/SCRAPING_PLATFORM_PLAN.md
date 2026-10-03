# Cariara's own scraping platform (instead of Apify)

Status: approved 2026-10-02. Build in the phases below, one commit each.

## Where we are

- **Apify contributes nothing.** 10 runs ever, all on 2026-09-14, $0.60 each;
  the $5 free tier ran out and the daily `apify-scrape-all` has done nothing
  since. As designed (131 Indeed searches a day) it would cost ~$80/day.
  None of the 57,938 active jobs or 5,304 contract jobs came from it.
- **We already run our own platform**: 252 registered scrapers (Workday 98,
  Greenhouse 64, Ashby 34, SmartRecruiters 6, Lever 5, Oracle, Phenom,
  Avature, iCIMS, Eightfold, Radancy, bespoke company sites, Meta GraphQL),
  Celery beat + workers, ScraperRun history. Every job board posting comes
  from an employer's career site, which these read directly.
- **The gaps** (from the code map):
  1. Two ingestion pipelines. Pipeline A (registry, scheduled, dedupe by
     company + id) and pipeline B (`IngestionSource`, admin "Refresh" only,
     synchronous, dedupe by ats + id, no run history). B overlaps A.
  2. Adding a company means a Python file. `/api/scrapers/custom/add` writes
     `scrapers/custom/<slug>.py` into the API container: lost on redeploy,
     never seen by the worker.
  3. Postings removed from a board stay active until a 14-day sweep.
  4. Fetching: per-process, per-slug rate limiting only; no Retry-After;
     no robots.txt for generic career pages; Lever and SmartRecruiters
     descriptions left to the 30-minute backfill.
  5. Monitoring is one global success rate; no per-board "stale" alert.

## Principles

- Read employers' own career systems through the public job interfaces
  they publish (ATS JSON APIs, schema.org JobPosting). Never defeat bot
  protection, solve CAPTCHAs or rotate residential proxies; no LinkedIn or
  Indeed scraping.
- Be polite: per-host rate limits shared by all workers, honour
  Retry-After, honour robots.txt for HTML career pages, back off on errors.
- A company is data, not code: one row says which ATS and which board.
- One pipeline, one dedupe rule (company + external id), one run history.

## Phases

### 0. Retire Apify
Remove `tasks/apify_tasks.py`, `services/apify_service.py`,
`scrapers/apify/`, the registry category, beat/route/annotation entries,
`APIFY_API_TOKEN` config and `apify-client`. Keep old rows; nothing new.

### 1. Boards as data (`job_boards` table) + one detector
- Table `job_boards`: company name/slug, `ats` (greenhouse, lever, ashby,
  smartrecruiters, workday), `board` (token / tenant + site), careers_url,
  enabled.
- One generic registry scraper per row, built at run time from the existing
  mixins (`BoardScraper`), dispatched by `scrape_all_companies` like any
  other slug; results saved and recorded exactly like the coded scrapers.
- One detector (`services/ats_detect.py`) for a careers URL: URL patterns,
  then the page's links/scripts, then a probe of the candidate API (must
  return jobs). Replaces `/custom/add` code generation: the admin "Add
  company" saves a row.
- Coded scrapers stay; a board row for a slug that already has one is
  refused.

### 2. Descriptions in the list call where the API has them
Lever (`descriptionPlain` + lists), so fewer jobs wait for the backfill.

### 3. Polite fetching
Per-host token bucket in Redis (shared across workers), Retry-After on 429
and 503, robots.txt (cached 24 h) for HTML career pages fetched by the
generic extractor.

### 4. Close removed postings
After a complete, successful board scrape, jobs of that company + source not
in the result for 2 consecutive runs are marked inactive (guarded: never
when the run was partial, empty or truncated).

### 5. Health
Per-board freshness (last success, jobs found trend, consecutive failures),
`GET /api/scrapers/health` (stale boards, failing boards, by ATS), the daily
alert lists the boards that broke instead of one global rate.

### Later
- Generic schema.org JobPosting crawler (sitemap + JSON-LD) for company
  sites with no known ATS.
- Merge pipeline B into the boards table and delete it.
- Headless browser only for career sites that need JavaScript, run openly
  (no stealth), on the existing browser queue.
