"""
OpsTalent - opstalent.com/career (own Next.js site, GraphQL).

The career page posts the JobOfferSearch query to https://api.opstalent.com/graphql
(title, location, job type, category). The site has no per-offer page: offers open
in place on /career, so job_url is the career page with the offer id as fragment.
Mostly CX roles in Wroclaw; IT only keeps the Technology ones. Verified 2026-10-20.
"""

from scrapers.base import ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY
from ._own_site import OwnSiteStaffingScraper

API_URL = "https://api.opstalent.com/graphql"
QUERY = """query JobOfferSearch($query: String, $location: String, $jobCategoryId: Int, $jobTypeId: Int, $limit: Int, $start: Int) {
  jobOfferSearch(location: $location, keywords: $query, jobCategoryId: $jobCategoryId, jobTypeId: $jobTypeId, limit: $limit, start: $start) {
    id
    title { title_en }
    subtitle { subtitle_en }
    jobField { description_en }
    location { description_en }
    jobType { name_en }
    jobCategory { name_en }
  }
}"""


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class OpsTalentScraper(OwnSiteStaffingScraper):
    config = ScraperConfig(
        company_slug="opstalent",
        company_name="OpsTalent",
        careers_url="https://opstalent.com/career",
        scraper_type=ScraperType.HTTP,
        allow_empty=True,
    )
    AGENCY_NAME = "OpsTalent"
    IT_AMBIGUOUS_DEFAULT = False

    def it_view(self, raw):
        return {"title": (raw.get("title") or {}).get("title_en"),
                "category": " ".join(filter(None, [(raw.get("jobCategory") or {}).get("name_en"),
                                                   (raw.get("jobField") or {}).get("description_en")])) or None,
                "skills": None}

    def listing_items(self, payload):
        data = (payload or {}).get("data") or {}
        return self.expect_list(data, "jobOfferSearch")

    async def fetch_raw(self) -> list:
        body = {"operationName": "JobOfferSearch", "variables": {"query": "", "location": ""}, "query": QUERY}
        data = await self._http("POST", API_URL, json_body=body, headers={"Origin": "https://opstalent.com"})
        return self.take_it(self.listing_items(data))

    def parse_job(self, raw: dict):
        title = (raw.get("title") or {}).get("title_en")
        sub = (raw.get("subtitle") or {}).get("subtitle_en")
        return self.make_job(
            title=title,
            location=(raw.get("location") or {}).get("description_en"),
            job_url=f"https://opstalent.com/career#offer-{raw.get('id')}",
            external_job_id=raw.get("id"),
            description=sub or None,
            employment_type_raw=(raw.get("jobType") or {}).get("name_en"),
            department=(raw.get("jobCategory") or {}).get("name_en"),
        )
