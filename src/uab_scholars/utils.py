"""uab_scholars.utils

Utility helpers shared across the uab_scholars package.
"""
from __future__ import annotations

import re
import unicodedata
from typing import List, Tuple

__all__ = [
    "slugify",
    "clean_text",
    "get_name_variations",
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


# Common name mappings for variations (moved from tool file for consistency)
_COMMON_NAME_MAP = {
    "Jim": "James J.",
    "Kristen Allen-Watts": "Kristen Allen Watts",
    "Alex": "Alexander",
    "RJ": "Reaford J.",
    "Bill": "William L.",
    "Stan": "F. Stanford",
    "Matt": "Matthew",
    "Robert": "Robert A.",
    "Terry": "Terrence M.",
    "Ben": "Benjamin",
    "Yu-Mei": "Yu Mei",
}


def get_name_variations(full_name: str) -> List[Tuple[str, str]]:
    """Generate name variations for more robust searching.
    
    Returns a list of (first_name, last_name) tuples covering common
    variations like nicknames, hyphenated names, Jr/Sr suffixes, etc.
    """
    parts = full_name.split()
    if not parts:
        return []
    
    first, last = parts[0], parts[-1]
    variations: List[Tuple[str, str]] = [(first, last)]
    
    # Handle common nickname mappings
    if full_name in _COMMON_NAME_MAP:
        alt_name = _COMMON_NAME_MAP[full_name]
        alt_parts = alt_name.split()
        if len(alt_parts) > 1:
            variations.append((alt_parts[0], alt_parts[-1]))
            if len(alt_parts) > 2:
                variations.append((f"{alt_parts[0]} {alt_parts[1]}", alt_parts[-1]))
        else:
            variations.append((alt_name, last))
    
    # Handle hyphenated names
    if "-" in full_name:
        no_hyphen = full_name.replace("-", " ")
        no_hyphen_parts = no_hyphen.split()
        variations.append((no_hyphen_parts[0], no_hyphen_parts[-1]))
        if len(no_hyphen_parts) > 2:
            variations.append((no_hyphen_parts[0], f"{no_hyphen_parts[-2]} {no_hyphen_parts[-1]}"))
    
    # Handle Jr/Sr suffixes
    if "Jr" in last or "Sr" in last:
        base_last = last.replace("Jr", "").replace("Sr", "").strip()
        variations.append((first, base_last))
        variations.append((first, f"{base_last}, Jr."))
        variations.append((first, f"{base_last}, Sr."))
        if len(parts) > 2:
            variations.append((f"{first} {parts[1]}", base_last))
            variations.append((f"{first} {parts[1]}", f"{base_last}, Jr."))
            variations.append((f"{first} {parts[1]}", f"{base_last}, Sr."))
    
    # Handle middle initial
    if len(parts) > 2 and len(parts[-2]) == 1:
        variations.append((f"{first} {parts[-2]}", last))
    
    return variations 