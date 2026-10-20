"""
Board-string checks shared by the scrapers.ats modules (not a board type:
load_all skips modules whose name starts with "_").
"""
import re
from typing import Optional

# A public hostname (career sites live on the employer's own domain or an ATS subdomain).
HOST = re.compile(r"(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
# One URL path segment or ATS account token.
TOKEN = re.compile(r"[A-Za-z0-9_.\-]{1,120}")
_SEGMENT = re.compile(r"[A-Za-z0-9_.\-~]{1,80}")


def host_and_path(board: str, min_segments: int = 0, max_segments: int = 3) -> Optional[tuple[str, list[str]]]:
    """'host/seg/seg' -> (host, [seg, seg]), or None when the host or a segment is malformed."""
    parts = (board or "").strip().strip("/").split("/")
    host, segments = parts[0].lower(), parts[1:]
    if not HOST.fullmatch(host) or not (min_segments <= len(segments) <= max_segments):
        return None
    if not all(_SEGMENT.fullmatch(s) and s not in (".", "..") for s in segments):
        return None
    return host, segments


def site_url(board: str, min_segments: int = 0, max_segments: int = 3) -> Optional[str]:
    """'host/seg' -> 'https://host/seg' (None when malformed)."""
    parsed = host_and_path(board, min_segments, max_segments)
    if not parsed:
        return None
    host, segments = parsed
    return "/".join([f"https://{host}", *segments])


def is_token(board: str) -> bool:
    return bool(TOKEN.fullmatch(board or ""))


def join_place(*parts) -> str:
    """'City', 'State', 'Country' -> 'City, State, Country', skipping blanks and repeats."""
    out = []
    for part in parts:
        text = " ".join(str(part or "").split()).strip(" ,")
        if text and text.lower() not in (p.lower() for p in out):
            out.append(text)
    return ", ".join(out)


def remote_from(*texts) -> "Optional[str]":
    """remote / hybrid / on-site from free-text workplace labels, else None."""
    blob = " ".join(str(t or "") for t in texts).lower()
    if "hybrid" in blob:
        return "hybrid"
    if "remote" in blob or "telecommut" in blob:
        return "remote"
    if "on-site" in blob or "onsite" in blob or "on site" in blob or "in_office" in blob or "office" in blob:
        return "on-site"
    return None
