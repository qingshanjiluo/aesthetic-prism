# labeling/security.py (W9): rater_id whitelist - every path segment built from a
# rater_id MUST pass _validate_rater_id first. Blocks '..', '/', '\\', non-ASCII.
from __future__ import annotations

import re

_RATER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def _validate_rater_id(rater_id: str) -> str:
    """Return rater_id when it matches ^[A-Za-z0-9_-]{1,32}$ (ASCII, <=32 chars).

    Otherwise raise ValueError("invalid rater_id"); the HTTP layer maps that
    ValueError to 400. No '..', no path separators -> traversal impossible.
    """
    if not isinstance(rater_id, str) or not _RATER_ID_RE.match(rater_id):
        raise ValueError("invalid rater_id")
    return rater_id
