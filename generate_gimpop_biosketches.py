#!/usr/bin/env python3
"""generate_gimpop_biosketches.py

Create plain-text biosketch summaries for all JSON profiles in `scholar_data/`.
Each output file is named `<Last, First> biosketch.txt` and written to
`output_bios/` (directory created if needed).

The script does *not* call OpenAI; it only uses the data already pulled
from Scholars@UAB. Edit as needed to add richer formatting.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "scholar_data"
OUT_DIR = ROOT / "output_bios"
OUT_DIR.mkdir(exist_ok=True)


def fmt_date(ts: int | str | None) -> str:
    if not ts:
        return ""
    if isinstance(ts, str) and ts.isdigit():
        ts = int(ts)
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
    except Exception:
        return str(ts)


def first_n(text: str, n: int = 400) -> str:
    return (text[: n - 3] + "...") if len(text) > n else text


def to_last_first(name: str) -> str:
    parts = name.split()
    if len(parts) >= 2:
        return f"{parts[-1]}, {' '.join(parts[:-1])}"
    return name


def write_bio(js_path: Path) -> None:
    data = json.loads(js_path.read_text())
    if data.get("status") != "success":
        return
    result = data["results"][0]
    p = result["profile"]

    name = p["name"]
    filename = OUT_DIR / f"{to_last_first(name)} biosketch.txt"

    lines: list[str] = []
    lines.append(name.upper())
    lines.append(p.get("position", ""))
    lines.append(p.get("department", ""))
    lines.append(p.get("url", ""))
    lines.append("")

    # Overview / bio
    bio = result.get("profile", {}).get("teaching_interests", "") or "Bio not available."
    lines.append("OVERVIEW:")
    lines.append(first_n(bio))
    lines.append("")

    # Publications
    pubs = result.get("publications", {}).get("recent", [])
    lines.append(f"RECENT PUBLICATIONS (showing {len(pubs)}):")
    for pub in pubs:
        lines.append(f"- {pub.get('year','')} {pub.get('title','')}")
    lines.append("")

    # Grants
    grants_total = result.get("grants", {}).get("total", 0)
    lines.append(f"GRANTS: {grants_total} total")
    lines.append("")

    # Teaching activities
    teach_total = result.get("teaching_activities", {}).get("total", 0)
    if teach_total:
        lines.append(f"TEACHING ACTIVITIES: {teach_total} recorded")
        lines.append("")

    filename.write_text("\n".join(lines), encoding="utf-8")
    print("📄", filename.name)


def main() -> None:
    files = sorted(DATA_DIR.glob("*_profile_*.json"))
    if not files:
        raise SystemExit("No profile JSON files found in scholar_data – run fetch script first.")
    for f in files:
        write_bio(f)
    print(f"\nGenerated {len(files)} biosketches in {OUT_DIR}/")


if __name__ == "__main__":
    main() 