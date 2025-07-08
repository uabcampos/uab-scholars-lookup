"""uab_scholars.utils

Utility helpers shared across the uab_scholars package.
"""
from __future__ import annotations

import re
import unicodedata

__all__ = [
    "slugify",
    "clean_text",
]


_dash_re = re.compile(r"[^a-z0-9\s-]")
_ws_re = re.compile(r"\s+")


def slugify(text: str) -> str:
    """Return a filesystem/API-safe slug: lowercase, ASCII, hyphen-separated."""
    text_norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text_norm = _dash_re.sub("", text_norm.lower())  # drop punctuation
    text_norm = _ws_re.sub("-", text_norm)
    return re.sub(r"-{2,}", "-", text_norm).strip("-")


def clean_text(s: str) -> str:
    """Unicode-normalise, replace smart quotes/dashes, collapse whitespace."""
    if not isinstance(s, str):
        return ""
    t = unicodedata.normalize("NFKC", s).replace("‚Äì", "-")
    for orig, repl in [
        ("\u2013", "-"),  # en-dash
        ("\u2014", "-"),  # em-dash
        ("\u201C", '"'), ("\u201D", '"'),
        ("\u2018", "'"), ("\u2019", "'"),
    ]:
        t = t.replace(orig, repl)
    return " ".join(t.split()) 