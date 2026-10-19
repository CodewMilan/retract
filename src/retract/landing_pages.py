"""Prebuilt marketing page served at /.

The workspace UI stays in retract.web and is opened from /dashboard.
"""

from importlib.resources import files
from pathlib import Path
import logging
import re


logger = logging.getLogger(__name__)
LANDING_CSP = (
    "default-src 'self'; script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data:; mask-src 'self' data:; connect-src 'self'; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)
_ASSET = re.compile(r"assets/[A-Za-z0-9._-]{1,120}\Z")
_FONT = re.compile(r"fonts/[a-z0-9-]{1,80}\.woff2\Z")
_MIME = {
    ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
    ".svg": "image/svg+xml", ".ico": "image/x-icon", ".woff2": "font/woff2",
}
# These names belong to the workspace UI and must not be replaced by the landing bundle.
_RESERVED = {"assets/dashboard.css", "assets/dashboard.mjs", "assets/dashboard-model.mjs", "assets/auth.mjs"}
_missing_logged = False


def landing_root():
    packaged = files("retract").joinpath("site")
    try:
        if packaged.joinpath("index.html").is_file():
            return packaged
    except OSError:
        pass
    dist = Path(__file__).resolve().parents[2] / "landing" / "dist"
    if (dist / "index.html").is_file():
        return dist
    return None


def warn_missing_landing():
    global _missing_logged
    if _missing_logged:
        return
    _missing_logged = True
    logger.warning("Landing build is missing; / cannot be served. The workspace stays at /dashboard")


def landing_asset(path: str):
    """Return body, mime, and cache policy for one hosted landing file."""
    root = landing_root()
    if root is None or not path.startswith("/"):
        return None
    rel = "index.html" if path == "/" else path[1:]
    if rel != "index.html" and (rel in _RESERVED or not (_ASSET.fullmatch(rel) or _FONT.fullmatch(rel))):
        return None
    candidate = root.joinpath(*rel.split("/"))
    try:
        if not candidate.is_file():
            return None
        body = candidate.read_bytes()
    except OSError:
        return None
    mime = _MIME.get(Path(rel).suffix)
    if mime is None:
        return None
    return body, mime, "no-store" if rel == "index.html" else "public, max-age=86400"
