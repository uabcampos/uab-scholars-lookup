#!/usr/bin/env python3
# pull_master_scholars_by_dept_concurrent.py

"""
Concurrently scan user IDs 1..MAX_ID, filter by DEPARTMENT substring,
then pull full profile, publications, grants, and teaching activities.
Clean bio, research interests, and teaching summary of unusual characters.

Outputs four CSVs:
- profiles_YYYYMMDD_HHMMSS.csv
- publications_YYYYMMDD_HHMMSS.csv
- grants_YYYYMMDD_HHMMSS.csv
- teaching_activities_YYYYMMDD_HHMMSS.csv
"""

import csv
import requests
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
from datetime import datetime

# —— CONFIG —— 
DEPARTMENT        = "Med - Preventive Medicine"  # substring to match
MAX_ID            = 6000                         # numeric IDs to scan
SCAN_WORKERS      = 20                           # threads for ID scanning
FETCH_WORKERS     = 10                           # threads for data fetching
SEARCH_PAGE_SIZE  = 500                          # page size for linkedTo calls
PAUSE_SECONDS     = 0.1                          # delay between paged calls

# Add timestamp to filenames
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

API_USER_DETAIL   = "https://scholars.uab.edu/api/users/{}"
API_PUBS          = "https://scholars.uab.edu/api/publications/linkedTo"
API_GRANTS        = "https://scholars.uab.edu/api/grants/linkedTo"
API_TEACHING      = "https://scholars.uab.edu/api/teachingActivities/linkedTo"

HEADERS = {
    "Accept":       "application/json, text/html, */*",
    "Content-Type": "application/json",
    "User-Agent":   "Mozilla/5.0"
}

# —— OUTPUT FILES —— 
PROFILES_CSV     = f"profiles_{TIMESTAMP}.csv"
PUBLICATIONS_CSV = f"publications_{TIMESTAMP}.csv"
GRANTS_CSV       = f"grants_{TIMESTAMP}.csv"
TEACHING_CSV     = f"teaching_activities_{TIMESTAMP}.csv"

# —— CSV FIELDNAMES —— 
PROFILE_FIELDS = [
    "objectId","discoveryUrlId","firstName","lastName",
    "email","orcid","department","positions",
    "bio","researchInterests","teachingSummary"
]
PUB_FIELDS = [
    "userObjectId","publicationObjectId","title","journal","doi",
    "pubYear","pubMonth","pubDay","volume","issue","pages","issn",
    "labels","authors"
]
GRANT_FIELDS = [
    "userObjectId","grantObjectId","title","funder",
    "awardType","year","month","day","labels"
]
TEACH_FIELDS = [
    "userObjectId","teachingActivityObjectId","type",
    "startYear","startMonth","startDay",
    "endYear","endMonth","endDay","title"
]

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
        ("\"", '"'), ("\"", '"'),
        ("'", "'"), ("'", "'"),
    ]
    for orig, repl in subs:
        t = t.replace(orig, repl)
    # collapse whitespace
    return " ".join(t.split())

def scan_match_ids(uid: int) -> Optional[str]:
    """
    Phase 1: fetch user detail by numeric ID.
    If any position.department contains DEPARTMENT, return discoveryUrlId.
    """
    try:
        r = session.get(API_USER_DETAIL.format(uid), headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return None
        js = r.json()
        for p in js.get("positions", []):
            if DEPARTMENT.lower() in (p.get("department","") or "").lower():
                return js.get("discoveryUrlId")
    except Exception:
        pass
    return None

def extract_profile(js: Dict[str, Any]) -> Dict[str, Any]:
    """Pull and clean profile fields from user JSON."""
    email = js.get("emailAddress", {}).get("address", "")
    orcid = js.get("orcid", "")
    depts = [p["department"].strip() for p in js.get("positions", []) if p.get("department")]
    titles = [p["position"].strip() for p in js.get("positions", []) if p.get("position")]
    for appt in js.get("institutionalAppointments", []):
        pos = appt.get("position")
        if pos:
            titles.append(pos.strip())

    # research interests
    raw_ri = js.get("researchInterests", "")
    research: List[str] = []
    if isinstance(raw_ri, str) and raw_ri.strip():
        research.append(clean_text(raw_ri))
    elif isinstance(raw_ri, list):
        for item in raw_ri:
            if isinstance(item, str):
                research.append(clean_text(item))
            elif isinstance(item, dict):
                v = item.get("value") or item.get("text") or ""
                research.append(clean_text(v))

    bio_clean = clean_text(js.get("overview", ""))
    teach_clean = clean_text(js.get("teachingSummary", ""))

    return {
        "objectId":          js.get("objectId", ""),
        "discoveryUrlId":    js.get("discoveryUrlId", ""),
        "firstName":         js.get("firstName", ""),
        "lastName":          js.get("lastName", ""),
        "email":             email,
        "orcid":             orcid,
        "department":        "; ".join(sorted(set(depts))),
        "positions":         "; ".join(sorted(set(titles))),
        "bio":               bio_clean,
        "researchInterests": "; ".join(research),
        "teachingSummary":   teach_clean,
    }

def fetch_pages(endpoint: str, payload_fn, per_page: int):
    """
    Helper to page through linkedTo endpoints.
    Yields each item dict.
    """
    start = 0
    while True:
        payload = payload_fn(start)
        r = session.post(endpoint, json=payload, headers=HEADERS, timeout=30)
        r.raise_for_status()
        blob = r.json()
        items = blob.get("items") or blob.get("resource") or []
        if not items:
            return
        for it in items:
            yield it
        total = blob.get("pagination", {}).get("total", 0)
        start += per_page
        if start >= total:
            return

def flatten_pub(pub: Dict[str, Any], uid: str) -> Dict[str, Any]:
    """Map publication JSON to flat CSV row."""
    authors = "; ".join(a.get("fullName", "") for a in pub.get("authors", []))
    labels  = "; ".join(l.get("value", "") for l in pub.get("labels", []))
    pd = pub.get("publicationDate", {})
    return {
        "userObjectId":        uid,
        "publicationObjectId": pub.get("objectId", ""),
        "title":               clean_text(pub.get("title", "")),
        "journal":             pub.get("journal", ""),
        "doi":                 pub.get("doi", ""),
        "pubYear":             pd.get("year", ""),
        "pubMonth":            pd.get("month", ""),
        "pubDay":              pd.get("day", ""),
        "volume":              pub.get("volume", ""),
        "issue":               pub.get("issue", ""),
        "pages":               pub.get("pagination", ""),
        "issn":                pub.get("issn", ""),
        "labels":              labels,
        "authors":             authors,
    }

def flatten_gr(gr: Dict[str, Any], uid: str) -> Dict[str, Any]:
    """Map grant JSON to flat CSV row."""
    d = gr.get("date1", {})
    labels = "; ".join(l.get("value", "") for l in gr.get("labels", []))
    return {
        "userObjectId":  uid,
        "grantObjectId": gr.get("objectId", ""),
        "title":         clean_text(gr.get("title", "")),
        "funder":        gr.get("funderName", ""),
        "awardType":     gr.get("objectTypeDisplayName", ""),
        "year":          d.get("year", ""),
        "month":         d.get("month", ""),
        "day":           d.get("day", ""),
        "labels":        labels,
    }

def flatten_teach(act: Dict[str, Any], uid: str) -> Dict[str, Any]:
    """Map teaching activity JSON to flat CSV row."""
    d1 = act.get("date1", {})
    d2 = act.get("date2", {})
    return {
        "userObjectId":             uid,
        "teachingActivityObjectId": act.get("objectId", ""),
        "type":                     act.get("objectTypeDisplayName", ""),
        "startYear":                d1.get("year", ""),
        "startMonth":               d1.get("month", ""),
        "startDay":                 d1.get("day", ""),
        "endYear":                  d2.get("year", ""),
        "endMonth":                 d2.get("month", ""),
        "endDay":                   d2.get("day", ""),
        "title":                    clean_text(act.get("title", "")),
    }

def process_user(disc_id: str) -> Dict[str, Any]:
    """Fetch detail and linked data for a single user, flatten all records."""
    js = session.get(API_USER_DETAIL.format(disc_id), headers=HEADERS, timeout=15).json()
    prof = extract_profile(js)
    uid = prof["objectId"]

    pubs = [
        flatten_pub(p, uid)
        for p in fetch_pages(
            API_PUBS,
            lambda s: {
                "objectId":      disc_id,
                "objectType":    "user",
                "pagination":    {"perPage": SEARCH_PAGE_SIZE, "startFrom": s},
                "favouritesFirst": True,
                "sort":          "dateDesc"
            },
            SEARCH_PAGE_SIZE
        )
    ]

    grants = [
        flatten_gr(g, uid)
        for g in fetch_pages(
            API_GRANTS,
            lambda s: {
                "objectId":   disc_id,
                "objectType": "user",
                "pagination": {"perPage": SEARCH_PAGE_SIZE, "startFrom": s}
            },
            SEARCH_PAGE_SIZE
        )
    ]

    teaching = [
        flatten_teach(t, uid)
        for t in fetch_pages(
            API_TEACHING,
            lambda s: {
                "objectId":   disc_id,
                "objectType": "user",
                "pagination": {"perPage": SEARCH_PAGE_SIZE, "startFrom": s}
            },
            SEARCH_PAGE_SIZE
        )
    ]

    return {
        "profile": prof,
        "publications": pubs,
        "grants": grants,
        "teaching": teaching
    }

def main():
    # Phase 1: scan IDs to find matching discoveryUrlIds
    print(f"Scanning IDs 1..{MAX_ID} for {DEPARTMENT}...")
    with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as pool:
        futures = {pool.submit(scan_match_ids, uid): uid for uid in range(1, MAX_ID+1)}
        disc_ids = []
        for fut in as_completed(futures):
            disc_id = fut.result()
            if disc_id:
                disc_ids.append(disc_id)
                print(f"Found {disc_id}")

    if not disc_ids:
        print("No matching users found.")
        return

    print(f"\nFound {len(disc_ids)} users. Fetching full data...")

    # Phase 2: fetch and flatten all data
    all_data = []
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        futures = {pool.submit(process_user, disc_id): disc_id for disc_id in disc_ids}
        for fut in as_completed(futures):
            try:
                data = fut.result()
                all_data.append(data)
                print(f"✓ {data['profile']['lastName']}, {data['profile']['firstName']}")
            except Exception as e:
                print(f"✗ Error processing {fut.disc_id}: {e}")

    # Phase 3: write CSVs
    print("\nWriting CSVs...")

    # profiles
    with open(PROFILES_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PROFILE_FIELDS)
        writer.writeheader()
        for data in all_data:
            writer.writerow(data["profile"])
    print(f"Wrote {PROFILES_CSV}")

    # publications
    with open(PUBLICATIONS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PUB_FIELDS)
        writer.writeheader()
        for data in all_data:
            writer.writerows(data["publications"])
    print(f"Wrote {PUBLICATIONS_CSV}")

    # grants
    with open(GRANTS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=GRANT_FIELDS)
        writer.writeheader()
        for data in all_data:
            writer.writerows(data["grants"])
    print(f"Wrote {GRANTS_CSV}")

    # teaching activities
    with open(TEACHING_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TEACH_FIELDS)
        writer.writeheader()
        for data in all_data:
            writer.writerows(data["teaching"])
    print(f"Wrote {TEACHING_CSV}")

if __name__ == "__main__":
    main()