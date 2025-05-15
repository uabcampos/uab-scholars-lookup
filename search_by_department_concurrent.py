#!/usr/bin/env python3
# search_by_department_concurrent.py

"""
Scan all Scholars@UAB user IDs concurrently, filter by department substring,
and write a single CSV sorted by last name.

Uses ThreadPoolExecutor to speed up the 1..MAX_ID fetches.
"""

import csv
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, Any
from datetime import datetime
import unicodedata

# —— CONFIG —— 
DEPARTMENT = "Med - Preventive Medicine"  # substring to match
MAX_ID     = 6000                         # upper bound on numeric user IDs
WORKERS    = 20                           # number of threads to use

# Add timestamp to filenames
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

API_USER   = "https://scholars.uab.edu/api/users/{}"
OUTPUT_CSV = f"users_by_department_{TIMESTAMP}.csv"

FIELDNAMES = [
    "objectId",
    "discoveryUrlId",
    "firstName",
    "lastName",
    "email",
    "department",
    "positions"
]

HEADERS = {
    "Accept":      "application/json, text/html, */*",
    "Content-Type": "application/json",
    "User-Agent":  "UAB-Scholars-Tool/1.0"
}

session = requests.Session()

def clean_text(s: str) -> str:
    """Normalize text and replace fancy punctuation with plain ASCII."""
    if not isinstance(s, str):
        return ""
    # normalize unicode
    t = unicodedata.normalize("NFKC", s)
    # replace mojibake sequence
    t = t.replace("‚Äì", "-")
    # replace en/em dashes and curly quotes
    subs = [
        ("\u2013", "-"), ("\u2014", "-"),
        (""", '"'), (""", '"'),
        ("'", "'"), ("'", "'"),
    ]
    for orig, repl in subs:
        t = t.replace(orig, repl)
    # collapse whitespace
    return " ".join(t.split())

def fetch_and_filter(uid: int) -> Optional[Dict[str, Any]]:
    """
    Fetch /api/users/{uid}, and if any position.department contains
    DEPARTMENT (case-insensitive), return a dict of fields; else None.
    """
    try:
        resp = session.get(API_USER.format(uid), headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        js = resp.json()
        positions = js.get("positions", [])
        matches = [
            p for p in positions
            if DEPARTMENT.lower() in (p.get("department","") or "").lower()
        ]
        if not matches:
            return None

        # collect unique department names and position titles
        depts = sorted({ p["department"].strip() for p in matches if p.get("department") })
        titles = sorted({ p["position"].strip() for p in positions if p.get("position") })

        return {
            "objectId":       js.get("objectId", ""),
            "discoveryUrlId": js.get("discoveryUrlId", ""),
            "firstName":      js.get("firstName", ""),
            "lastName":       js.get("lastName", ""),
            "email":          js.get("emailAddress", {}).get("address", ""),
            "department":     "; ".join(depts),
            "positions":      "; ".join(titles),
        }
    except Exception as e:
        print(f"Error fetching user {uid}: {str(e)}")
        return None

def main():
    results = []

    # dispatch concurrent fetches
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = { pool.submit(fetch_and_filter, uid): uid for uid in range(1, MAX_ID+1) }
        for fut in as_completed(futures):
            record = fut.result()
            if record:
                results.append(record)

    # sort by lastName then firstName
    results.sort(key=lambda r: (r["lastName"].lower(), r["firstName"].lower()))

    # write to CSV
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)

    print(f"✔ Done! Found {len(results)} users. Output → {OUTPUT_CSV}")

if __name__ == "__main__":
    main()