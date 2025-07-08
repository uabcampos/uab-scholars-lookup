#!/usr/bin/env python3
"""parse_gimpop_faculty.py

Read `gimpop-faculty.txt` and produce a cleaned list of faculty names in
"First Middle Last" order (degrees and credentials removed). The cleaned
names are written to `cleaned_faculty_names.txt` and also printed to
stdout so that downstream scripts can import or shell-pipe them.
"""

from __future__ import annotations

import re
from pathlib import Path
import sys

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
SOURCE_FILE = ROOT / "gimpop-faculty.txt"
OUT_FILE = ROOT / "cleaned_faculty_names.txt"

# Regex pattern for leading bullet + whitespace
BULLET_RE = re.compile(r"^[\s\u2022\-•\t]*")


def clean_line(line: str) -> str | None:
    """Convert a raw line to "First Last"; return None if parsing fails."""
    line = BULLET_RE.sub("", line).strip()
    if not line:
        return None

    # Split by comma: expecting "Last, First Middle, [credentials…]"
    parts = [p.strip() for p in line.split(",") if p.strip()]
    if len(parts) < 2:
        return None
    last, first_and_more = parts[0], parts[1]
    # Ignore any additional comma-separated parts (credentials, suffixes)
    name = f"{first_and_more} {last}"
    # Collapse multiple spaces
    name = re.sub(r"\s{2,}", " ", name).strip()
    return name


def main() -> None:
    if not SOURCE_FILE.exists():
        sys.exit(f"❌ Source file not found: {SOURCE_FILE}")

    cleaned: list[str] = []
    for raw in SOURCE_FILE.read_text(encoding="utf-8").splitlines():
        name = clean_line(raw)
        if name:
            cleaned.append(name)

    if not cleaned:
        sys.exit("❌ No names parsed. Check source format.")

    OUT_FILE.write_text("\n".join(cleaned), encoding="utf-8")
    print("\n".join(cleaned))
    print(f"\n✅ Parsed {len(cleaned)} faculty names → {OUT_FILE}")


if __name__ == "__main__":
    main() 