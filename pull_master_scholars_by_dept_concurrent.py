#!/usr/bin/env python3
# pull_master_scholars_by_dept_concurrent.py

"""
Concurrently scan user IDs 1..MAX_ID, filter by DEPARTMENT substring,
then pull full profile, publications, grants, and teaching activities.
Clean bio, research interests, and teaching summary of unusual characters.

Outputs four CSVs:
- profiles.csv
- publications.csv
- grants.csv
- teaching_activities.csv
"""

import csv
import requests
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

# —— CONFIG —— 
DEPARTMENT        = "Med - Preventive Medicine"  # substring to match
MAX_ID            = 6000                         # numeric IDs to scan
SCAN_WORKERS      = 20                           # threads for ID scanning
FETCH_WORKERS     = 10                           # threads for data fetching
SEARCH_PAGE_SIZE  = 500                          # page size for linkedTo calls
PAUSE_SECONDS     = 0.1                          # delay between paged calls

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
PROFILES_CSV     = "profiles.csv"
PUBLICATIONS_CSV = "publications.csv"
GRANTS_CSV       = "grants.csv"
TEACHING_CSV     = "teaching_activities.csv"

# —— CSV FIELDNAMES —— 
PROFILE_FIELDS = [
    "objectId","discoveryUrlId","firstName","lastName",
    "email","orcid","departments","positions",
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
        ("“", '"'), ("”", '"'),
        ("‘", "'"), ("’", "'"),
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
        "departments":       "; ".join(sorted(set(depts))),
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
        "title":               pub.get("title", ""),
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
        "title":         gr.get("title", ""),
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
        "title":                    act.get("title", ""),
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

    return {"profile": prof, "publications": pubs, "grants": grants, "teaching": teaching}

def main():
    # Phase 1: scan IDs to find matching discoveryUrlIds
    with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as scan_pool:
        scan_futs = [scan_pool.submit(scan_match_ids, uid) for uid in range(1, MAX_ID+1)]
        disc_ids = {fut.result() for fut in as_completed(scan_futs) if fut.result()}

    # Prepare CSV writers
    with open(PROFILES_CSV,     "w", newline="", encoding="utf-8") as pf, \
         open(PUBLICATIONS_CSV, "w", newline="", encoding="utf-8") as pbf, \
         open(GRANTS_CSV,       "w", newline="", encoding="utf-8") as gf, \
         open(TEACHING_CSV,     "w", newline="", encoding="utf-8") as tf:

        w_prof  = csv.DictWriter(pf, fieldnames=PROFILE_FIELDS);     w_prof.writeheader()
        w_pub   = csv.DictWriter(pbf, fieldnames=PUB_FIELDS);        w_pub.writeheader()
        w_gr    = csv.DictWriter(gf, fieldnames=GRANT_FIELDS);       w_gr.writeheader()
        w_teach = csv.DictWriter(tf, fieldnames=TEACH_FIELDS);       w_teach.writeheader()

        # Phase 2: fetch and write data for each user
        with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as fetch_pool:
            fetch_futs = {fetch_pool.submit(process_user, did): did for did in disc_ids}
            for fut in as_completed(fetch_futs):
                data = fut.result()
                w_prof.writerow(data["profile"])
                for row in data["publications"]:
                    w_pub.writerow(row)
                for row in data["grants"]:
                    w_gr.writerow(row)
                for row in data["teaching"]:
                    w_teach.writerow(row)

    print(f"✔ Done! Scanned {MAX_ID} IDs, found {len(disc_ids)} users, wrote CSVs.")

if __name__ == "__main__":
    main()