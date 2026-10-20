"""
More job systems for job_boards rows, one module per system.

Each module here calls register() with a BoardType: the mixin that scrapes
it, a check of the row's board string, the URL the scrape starts from, the
public board page, and the class attributes the mixin reads from the board.
board_scraper consults TYPES for any ats it does not handle itself, so a new
system is a new module, never an edit to board_scraper.

load_all() imports every module in this package so their register() calls run.
"""
import importlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BoardType:
    name: str                                  # the job_boards.ats value (at most 20 chars)
    mixin: type                                # supplies scrape() and parse_job()
    valid: Callable[[str], bool]               # is this board string usable?
    start_url: Callable[[str], str]            # where the scrape starts (the scraper's API_URL)
    careers_url: Callable[[str], Optional[str]] = lambda board: None  # public page for rows saved without one
    attrs: Callable[[str], dict] = field(default=lambda board: {})     # extra class attributes for the mixin
    browser: bool = False                      # runs a real browser: dispatched on the browser queue


TYPES: dict[str, BoardType] = {}
_loaded = False


def register(board_type: BoardType) -> BoardType:
    if len(board_type.name) > 20:
        raise ValueError(f"ats name {board_type.name!r} is longer than job_boards.ats allows")
    TYPES[board_type.name] = board_type
    return board_type


def load_all() -> dict[str, BoardType]:
    global _loaded
    if not _loaded:
        for module_path in sorted(Path(__file__).parent.glob("*.py")):
            if module_path.name.startswith("_"):
                continue
            try:
                importlib.import_module(f"scrapers.ats.{module_path.stem}")
            except Exception as e:
                logger.error(f"Failed to load scrapers.ats.{module_path.stem}: {e}")
        _loaded = True
    return TYPES


def get(ats: Optional[str]) -> Optional[BoardType]:
    return load_all().get(ats or "")
