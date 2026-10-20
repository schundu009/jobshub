"""Maxonic: its own JSON copy of its Ceipal postings."""
import asyncio

from contracts.scrapers.maxonic import MaxonicScraper

# The shape of maxonic.com/api/jobs.php (synthetic values).
FEED = {
    "source": "ceipal",
    "results": [
        {"id": "eXlzalQy", "title": "Senior Java Developer", "city": "Fremont", "state": "California",
         "remote": "", "type": "Contract", "posted": "2026-10-20",
         "applyUrl": "https://candidateportal.ceipal.com/job-details/abc"},
        {"id": "bm90SVQ", "title": "Material Handler", "city": "Milpitas", "state": "California",
         "remote": "", "type": "", "posted": "2026-10-20", "applyUrl": "https://candidateportal.ceipal.com/job-details/def"},
    ],
}


def test_maxonic_keeps_it_jobs_with_their_links(monkeypatch):
    async def http(self, method, url, **kwargs):
        assert url == "https://maxonic.com/api/jobs.php"
        return FEED

    monkeypatch.setattr(MaxonicScraper, "_http", http)

    async def run():
        async with MaxonicScraper() as s:
            return await s.scrape()

    result = asyncio.run(run())
    assert result.success
    assert [j.title for j in result.jobs] == ["Senior Java Developer"]
    job = result.jobs[0]
    assert job.location == "Fremont, California"
    assert job.job_url == "https://candidateportal.ceipal.com/job-details/abc"
    assert job.external_job_id == "eXlzalQy"
    assert job.employment_type_raw == "Contract"
