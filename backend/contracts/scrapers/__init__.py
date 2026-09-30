"""
Staffing-agency scrapers (registry category "staffing").

They register with ScraperRegistry like any scraper but are excluded from the
full-time scrape_all_companies and run by contracts.tasks.scrape_all_contracts.
load_all() imports every module in this package so the decorators run.
"""
import importlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

STAFFING_CATEGORY = "staffing"
_loaded = False


def load_all() -> None:
    global _loaded
    if _loaded:
        return
    for module_path in sorted(Path(__file__).parent.glob("*.py")):
        if module_path.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"contracts.scrapers.{module_path.stem}")
        except Exception as e:
            logger.error(f"Failed to load contracts.scrapers.{module_path.stem}: {e}")
    _loaded = True
