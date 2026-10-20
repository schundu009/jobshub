"""
Eightfold AI career sites as job_boards rows (ats "eightfold").

Board: "<site host>/<domain>", the host serving /careers and the domain=
parameter its searches send, e.g. "paypal.eightfold.ai/paypal.com" or
"jobs.ascendion.com/ascendion.com". Reuses EightfoldMixin. A site answers
either the newer /api/pcsx/search or the older /api/apply/v2/jobs (the other
says "not authorized"/"not enabled"), so the first page picks the one that
lists positions.
"""
from scrapers.ats import BoardType, register
from scrapers.ats._sitetext import HOST, host_and_path
from scrapers.base import ScrapeResult
from scrapers.enterprise.eightfold_scrapers import EightfoldMixin


def _parts(board: str):
    parsed = host_and_path(board, min_segments=1, max_segments=1)
    if not parsed or not HOST.fullmatch(parsed[1][0].lower()):
        return None
    return parsed[0], parsed[1][0].lower()


class EightfoldBoardMixin(EightfoldMixin):
    """EightfoldMixin that finds the site's API generation itself."""

    API_VARIANT = "pcsx"

    async def scrape(self) -> ScrapeResult:
        for variant in ("pcsx", "apply_v2"):
            self.API_VARIANT = variant
            try:
                body = self._unwrap(await self.fetch_json(self._search_url(), params=self._search_params(0)))
            except Exception as e:
                self.logger.info(f"Eightfold {variant} search refused: {e}")
                continue
            if isinstance(body.get("positions"), list):
                break
        return await super().scrape()


def _site(board: str) -> str:
    return f"https://{_parts(board)[0]}"


register(BoardType(
    name="eightfold",
    mixin=EightfoldBoardMixin,
    valid=lambda board: _parts(board) is not None,
    start_url=lambda board: f"{_site(board)}/api/pcsx/search?domain={_parts(board)[1]}",
    careers_url=lambda board: f"{_site(board)}/careers?domain={_parts(board)[1]}",
    attrs=lambda board: {"SITE_URL": _site(board), "DOMAIN": _parts(board)[1]},
))
