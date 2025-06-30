#!/usr/bin/env python3
# pull_master_scholars_by_faculty_list.py

"""
Master script: Pull complete Scholars@UAB profiles, publications, grants,
and teaching activities for a list of faculty by name and write to four CSVs:
- profiles_YYYYMMDD_HHMMSS.csv
- publications_YYYYMMDD_HHMMSS.csv
- grants_YYYYMMDD_HHMMSS.csv
- teaching_activities_YYYYMMDD_HHMMSS.csv

Requires a faculty_fullnames.py file with:
    faculty_fullnames = [
        "Andrea L Cherrington",
        "Camille Worthington",
        # etc.
    ]
"""

import csv
import time
import requests
import unicodedata
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional
import scholars_api_shim  # noqa: F401

from faculty_fullnames import faculty_fullnames

# ---- CONFIG --------------------------------------------------------------
BASE_URL             = "https://scholars.uab.edu"
API_USERS            = f"{BASE_URL}/api/users"
PUBS_API_URL         = f"{BASE_URL}/api/publications/linkedTo"
GRANTS_API_URL       = f"{BASE_URL}/api/grants/linkedTo"
TEACHING_API_URL     = f"{BASE_URL}/api/teachingActivities/linkedTo"

PER_PAGE_PUBS        = 500
PER_PAGE_GRANTS      = 500
PER_PAGE_TEACHING    = 500
PAUSE                = 0.1  # seconds between requests
MAX_WORKERS          = 10   # number of concurrent workers

API_HEADERS = {
    "Accept":       "application/json, text/html, */*",
    "Content-Type": "application/json",
    "User-Agent":   "UAB-Scholars-Tool/1.0"
}

# Get current timestamp for filenames
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# ---- OUTPUT FILES & FIELDS -----------------------------------------------
PROFILES_CSV      = f"profiles_{TIMESTAMP}.csv"
PUBLICATIONS_CSV  = f"publications_{TIMESTAMP}.csv"
GRANTS_CSV        = f"grants_{TIMESTAMP}.csv"
TEACHING_CSV      = f"teaching_activities_{TIMESTAMP}.csv"

PROFILE_FIELDS    = [
    "objectId", "discoveryUrlId", "firstName", "lastName",
    "email", "orcid", "department", "positions",
    "bio", "researchInterests", "teachingSummary"
]
PUB_FIELDS        = [
    "userObjectId", "publicationObjectId", "title", "journal", "doi",
    "pubYear", "pubMonth", "pubDay", "volume", "issue", "pages", "issn",
    "labels", "authors", "url"
]
GRANT_FIELDS      = [
    "userObjectId", "grantObjectId", "title", "funder",
    "awardType", "year", "month", "day", "labels", "url"
]
TEACH_FIELDS      = [
    "userObjectId", "teachingActivityObjectId", "type",
    "startYear", "startMonth", "startDay",
    "endYear", "endMonth", "endDay", "title", "url"
]

session = requests.Session()

# ---- CLEANING HELPER -----------------------------------------------------
def clean_text(s: str) -> str:
    """
    Normalize unicode (NFKC), replace mojibake ‚Äì with hyphens,
    convert curly quotes/dashes to plain ASCII, collapse whitespace.
    """
    if not isinstance(s, str):
        return ""
    t = unicodedata.normalize("NFKC", s)
    # mojibake
    t = t.replace("‚Äì", "-")
    # en/em dashes and curly quotes
    subs = [
        ("\u2013", "-"), ("\u2014", "-"),
        (""", '"'), (""", '"'),
        ("'", "'"), ("'", "'"),
    ]
    for orig, repl in subs:
        t = t.replace(orig, repl)
    # collapse spaces/newlines
    return " ".join(t.split())

# ---- FIND & FETCH --------------------------------------------------------
def get_name_variations(full_name: str) -> list:
    """
    Generate variations of a name to try different formats.
    Returns a list of (first, last) tuples to try.
    """
    parts = full_name.split()
    first, last = parts[0], parts[-1]
    variations = [(first, last)]  # Start with original format
    
    # Common name variations
    name_map = {
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
        "Yu-Mei": "Yu Mei"
    }
    
    # Handle special cases
    if full_name in name_map:
        alt_name = name_map[full_name]
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
    
    # Handle Jr./Sr.
    if "Jr" in last or "Sr" in last:
        base_last = last.replace("Jr", "").replace("Sr", "").strip()
        variations.append((first, base_last))
        variations.append((first, f"{base_last}, Jr."))
        variations.append((first, f"{base_last}, Sr."))
        if len(parts) > 2:
            variations.append((f"{first} {parts[1]}", base_last))
            variations.append((f"{first} {parts[1]}", f"{base_last}, Jr."))
            variations.append((f"{first} {parts[1]}", f"{base_last}, Sr."))
    
    # Try with middle initial if present
    if len(parts) > 2 and len(parts[-2]) == 1:
        variations.append((f"{first} {parts[-2]}", last))
    
    return variations

def find_disc_id(full_name: str) -> Optional[str]:
    """
    Try to find a user's discoveryUrlId using various name formats.
    """
    variations = get_name_variations(full_name)
    
    for first, last in variations:
        try:
            payload = {"params": {"by": "text", "type": "user", "text": f"{first} {last}"}}
            r = session.post(API_USERS, json=payload, headers=API_HEADERS, timeout=15)
            r.raise_for_status()
            
            for u in r.json().get("resource", []):
                if (u.get("firstName","").lower() == first.lower() and
                    u.get("lastName","").lower() == last.lower()):
                    return u.get("discoveryUrlId")
                
                if (u.get("lastName","").lower() == last.lower() and
                    (u.get("firstName","").lower().startswith(first.lower()) or
                     first.lower().startswith(u.get("firstName","").lower()))):
                    return u.get("discoveryUrlId")
        except Exception as e:
            print(f"Error searching for {full_name}: {str(e)}")
            continue
    
    return None

def fetch_user_js(disc_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch user JSON profile by discoveryUrlId.
    If the API returns a list, unwrap it.
    If the API returns {"resource": [...]}, unwrap that list.
    """
    try:
        r = session.get(f"{API_USERS}/{disc_id}", headers=API_HEADERS, timeout=15)
        r.raise_for_status()
        js = r.json()

        # Case A: API returns a bare list of user objects
        if isinstance(js, list):
            if not js:
                return None
            js = js[0]

        # Case B: API returns {"resource": [ {...} ]}
        elif isinstance(js, dict) and "resource" in js:
            resource = js.get("resource") or []
            if not isinstance(resource, list) or len(resource) == 0:
                return None
            js = resource[0]

        return js

    except Exception as e:
        print(f"Error fetching user {disc_id}: {str(e)}")
        return None

# ---- PROFILE EXTRACTION --------------------------------------------------
def extract_profile(js: Dict[str, Any]) -> Dict[str, Any]:
    email = js.get("emailAddress", {}).get("address", "")
    orcid = js.get("orcid", "")
    depts = [p["department"].strip() for p in js.get("positions", []) if p.get("department")]
    titles = [p["position"].strip() for p in js.get("positions", []) if p.get("position")]
    for appt in js.get("institutionalAppointments", []):
        if appt.get("position"):
            titles.append(appt["position"].strip())

    bio_clean = clean_text(js.get("overview", ""))
    teach_clean = clean_text(js.get("teachingSummary", ""))

    raw_ri = js.get("researchInterests", "")
    research = []
    if isinstance(raw_ri, str) and raw_ri.strip():
        research.append(clean_text(raw_ri))
    elif isinstance(raw_ri, list):
        for item in raw_ri:
            if isinstance(item, str):
                research.append(clean_text(item))
            elif isinstance(item, dict):
                v = item.get("value") or item.get("text") or item.get("description") or ""
                research.append(clean_text(v))

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

def fetch_all_pages(url: str, payload_fn, per_page: int):
    start = 0
    while True:
        try:
            payload = payload_fn(start)
            r = session.post(url, json=payload, headers=API_HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
            results = data.get("items") or data.get("resource") or []
            if not results:
                break
            yield results
            total = data.get("pagination", {}).get("total", 0)
            start += per_page
            if start >= total:
                break
            time.sleep(PAUSE)
        except Exception as e:
            print(f"Error fetching page {start} from {url}: {str(e)}")
            break

def flatten_publication(pub: Dict[str, Any], user_obj_id: str) -> Dict[str, Any]:
    authors = "; ".join(a.get("fullName", "") for a in pub.get("authors", []))
    labels  = "; ".join(l.get("value", "") for l in pub.get("labels", []))
    pd = pub.get("publicationDate", {})
    return {
        "userObjectId":        user_obj_id,
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
        "url":                 pub.get("url", ""),
    }

def flatten_grant(gr: Dict[str, Any], user_obj_id: str) -> Dict[str, Any]:
    d = gr.get("date1", {})
    labels = "; ".join(l.get("value", "") for l in gr.get("labels", []))
    return {
        "userObjectId":  user_obj_id,
        "grantObjectId": gr.get("objectId", ""),
        "title":         clean_text(gr.get("title", "")),
        "funder":        gr.get("funderName", ""),
        "awardType":     gr.get("objectTypeDisplayName", ""),
        "year":          d.get("year", ""),
        "month":         d.get("month", ""),
        "day":           d.get("day", ""),
        "labels":        labels,
        "url":           gr.get("url", ""),
    }

def flatten_teaching(act: Dict[str, Any], user_obj_id: str) -> Dict[str, Any]:
    d1 = act.get("date1", {})
    d2 = act.get("date2", {})
    return {
        "userObjectId":             user_obj_id,
        "teachingActivityObjectId": act.get("objectId", ""),
        "type":                     act.get("objectTypeDisplayName", ""),
        "startYear":                d1.get("year", ""),
        "startMonth":               d1.get("month", ""),
        "startDay":                 d1.get("day", ""),
        "endYear":                  d2.get("year", ""),
        "endMonth":                 d2.get("month", ""),
        "endDay":                   d2.get("day", ""),
        "title":                    clean_text(act.get("title", "")),
        "url":                      act.get("url", ""),
    }

def process_user(disc_id: str) -> Optional[Dict[str, Any]]:
    """Fetch and process all data for a single user."""
    try:
        js = fetch_user_js(disc_id)
        if not js:
            return None

        prof = extract_profile(js)
        uid = prof["objectId"]

        # --- Publications: fetch pages, then flatten each publication dict ---
        pubs = []
        for page in fetch_all_pages(
            PUBS_API_URL,
            lambda s: {
                "objectId":       disc_id,
                "objectType":     "user",
                "pagination":     {"perPage": PER_PAGE_PUBS, "startFrom": s},
                "favouritesFirst": True,
                "sort":           "dateDesc"
            },
            PER_PAGE_PUBS
        ):
            for p in page:
                pubs.append(flatten_publication(p, uid))

        # --- Grants: same pattern ---
        grants = []
        for page in fetch_all_pages(
            GRANTS_API_URL,
            lambda s: {
                "objectId":   disc_id,
                "objectType": "user",
                "pagination": {"perPage": PER_PAGE_GRANTS, "startFrom": s}
            },
            PER_PAGE_GRANTS
        ):
            for g in page:
                grants.append(flatten_grant(g, uid))

        # --- Teaching activities: same pattern ---
        teaching = []
        for page in fetch_all_pages(
            TEACHING_API_URL,
            lambda s: {
                "objectId":   disc_id,
                "objectType": "user",
                "pagination": {"perPage": PER_PAGE_TEACHING, "startFrom": s}
            },
            PER_PAGE_TEACHING
        ):
            for t in page:
                teaching.append(flatten_teaching(t, uid))

        return {
            "profile":      prof,
            "publications": pubs,
            "grants":       grants,
            "teaching":     teaching
        }
    except Exception as e:
        print(f"Error processing user {disc_id}: {str(e)}")
        return None

def main():
    # Find discoveryUrlIds for all faculty
    print(f"Searching for {len(faculty_fullnames)} faculty...")
    disc_ids = []
    for name in faculty_fullnames:
        disc_id = find_disc_id(name)
        if disc_id:
            disc_ids.append(disc_id)
            print(f"Found {name} → {disc_id}")
        else:
            print(f"Not found: {name}")

    if not disc_ids:
        print("No matching users found.")
        return

    print(f"\nFound {len(disc_ids)} users. Fetching full data...")

    # Fetch and process all data
    all_profiles = []
    all_pubs = []
    all_grants = []
    all_teaching = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(process_user, disc_id): disc_id for disc_id in disc_ids}
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                all_profiles.append(result["profile"])
                all_pubs.extend(result["publications"])
                all_grants.extend(result["grants"])
                all_teaching.extend(result["teaching"])

    # Write CSVs
    print(f"\nWriting {len(all_profiles)} profiles...")
    with open(PROFILES_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PROFILE_FIELDS)
        writer.writeheader()
        writer.writerows(all_profiles)

    print(f"Writing {len(all_pubs)} publications...")
    with open(PUBLICATIONS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PUB_FIELDS)
        writer.writeheader()
        writer.writerows(all_pubs)

    print(f"Writing {len(all_grants)} grants...")
    with open(GRANTS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=GRANT_FIELDS)
        writer.writeheader()
        writer.writerows(all_grants)

    print(f"Writing {len(all_teaching)} teaching activities...")
    with open(TEACHING_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TEACH_FIELDS)
        writer.writeheader()
        writer.writerows(all_teaching)

    print("Done!")

if __name__ == "__main__":
    main()