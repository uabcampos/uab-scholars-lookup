#!/usr/bin/env python3
# cdtr_collaboration_pull.py
"""
Pull complete Scholars@UAB profiles for a list of CDTR faculty members from a CSV file,
using robust name search to find discoveryUrlId, and output all available data.
"""

import csv
import time
import requests
import unicodedata
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import scholars_api_shim  # noqa: F401

# ---- CONFIG --------------------------------------------------------------
INPUT_CSV = "CDTR_MemberBase_Cleaned.csv"  # Input CSV file with faculty names
PER_PAGE_PUBS = 500                        # publications per page
PER_PAGE_GRANTS = 500                      # grants per page
PER_PAGE_TEACHING = 500                    # teaching activities per page
PAUSE = 0.1                               # seconds between page fetches
MAX_WORKERS = 8

# Add timestamp to filenames
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

API_BASE = "https://scholars.uab.edu/api"
USERS_API_BASE = f"{API_BASE}/users/{{}}"
USERS_API_SEARCH = f"{API_BASE}/users"
PUBS_API_URL = f"{API_BASE}/publications/linkedTo"
GRANTS_API_URL = f"{API_BASE}/grants/linkedTo"
TEACH_API_URL = f"{API_BASE}/teachingActivities/linkedTo"

HEADERS = {
    "User-Agent": "UAB-Scholars-Tool/1.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

PROFILES_CSV = f"profiles_{TIMESTAMP}.csv"
PUBLICATIONS_CSV = f"publications_{TIMESTAMP}.csv"
GRANTS_CSV = f"grants_{TIMESTAMP}.csv"
TEACHING_CSV = f"teaching_activities_{TIMESTAMP}.csv"

# ---- MANUAL OVERRIDES ---------------------------------------------------
# Map of 'PI Name' (as in CSV) to correct discoveryUrlId
MANUAL_DISCOVERY_IDS = {
    'Allen Watts, Kristen': '12139-kristen-allen-watts',
    'Cedillo, Yenni': '17388-yenni-cedillo-juarez',
    # Add more overrides here if needed
}

# ---- NAME SEARCH HELPERS -------------------------------------------------
def get_name_variations(first_last: str) -> List[str]:
    """Generate variations of a name for searching (expects 'First Middle Last')."""
    names = first_last.split()
    variations = []
    if len(names) >= 2:
        # Full name
        variations.append(' '.join(names))
        # First + Last only
        variations.append(f"{names[0]} {names[-1]}")
        # First initial + Last
        variations.append(f"{names[0][0]} {names[-1]}")
        # If middle name/initial present
        if len(names) > 2:
            variations.append(f"{names[0]} {names[1][0]} {names[-1]}")
    elif len(names) == 1:
        variations.append(names[0])
    return variations

def find_user_id(first_last: str) -> Optional[str]:
    """Find a user's discoveryUrlId using various name formats (expects 'First Middle Last')."""
    variations = get_name_variations(first_last)
    for search_query in variations:
        print(f"Trying: {search_query}")
        try:
            payload = {
                "params": {
                    "by": "text",
                    "type": "user",
                    "text": search_query
                }
            }
            response = requests.post(USERS_API_SEARCH, json=payload, headers=HEADERS, timeout=15)
            response.raise_for_status()
            data = response.json()
            if data and "resource" in data:
                for user in data["resource"]:
                    # Exact match on first and last name
                    if (user.get("firstName", "").lower() == search_query.split()[0].lower() and
                        user.get("lastName", "").lower() == search_query.split()[-1].lower()):
                        return user.get("discoveryUrlId")
                    # Partial match (first name in user first name, last name exact)
                    if (search_query.split()[0].lower() in user.get("firstName", "").lower() and
                        user.get("lastName", "").lower() == search_query.split()[-1].lower()):
                        return user.get("discoveryUrlId")
        except Exception as e:
            print(f"Error searching for {search_query}: {str(e)}")
            continue
    return None

# ---- CLEANING HELPER -----------------------------------------------------
def clean_text(s: str) -> str:
    """Normalize unicode, replace mojibake and fancy punctuation, collapse whitespace."""
    if not isinstance(s, str):
        return ""
    t = unicodedata.normalize("NFKC", s)
    t = t.replace("‚Äì", "-")
    for orig, repl in [
        ("\u2013", "-"), ("\u2014", "-"),
        (""", '"'), (""", '"'),
        ("'", "'"), ("'", "'"),
    ]:
        t = t.replace(orig, repl)
    return " ".join(t.split())

# ---- FETCH FUNCTIONS -----------------------------------------------------
def fetch_user_js(disc_id: str) -> Optional[Dict[str, Any]]:
    """Fetch user JSON profile by discoveryUrlId."""
    try:
        resp = requests.get(USERS_API_BASE.format(disc_id), headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error fetching user {disc_id}: {str(e)}")
        return None

def fetch_all_pages(url: str, payload_fn, per_page: int):
    start = 0
    while True:
        try:
            payload = payload_fn(start)
            resp = requests.post(url, json=payload, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            data = resp.json()
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

# ---- FLATTEN HELPERS -----------------------------------------------------
def extract_profile(js: Dict[str, Any]) -> Dict[str, Any]:
    email = js.get("emailAddress", {}).get("address", "")
    orcid = js.get("orcid", "") or ""
    depts = [p.get("department", "").strip() for p in js.get("positions", []) if p.get("department")]
    titles = [p.get("position", "").strip() for p in js.get("positions", []) if p.get("position")]
    for appt in js.get("institutionalAppointments", []):
        if appt.get("position"):
            titles.append(appt["position"].strip())
    bio_clean = clean_text(js.get("overview", "").replace("\n", " "))
    teach_clean = clean_text(js.get("teachingSummary", "").replace("\n", " "))
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
        "objectId": js.get("objectId", ""),
        "discoveryUrlId": js.get("discoveryUrlId", ""),
        "firstName": js.get("firstName", ""),
        "lastName": js.get("lastName", ""),
        "email": email,
        "orcid": orcid,
        "department": "; ".join(sorted(set(depts))),
        "positions": "; ".join(sorted(set(titles))),
        "bio": bio_clean,
        "researchInterests": "; ".join(research),
        "teachingSummary": teach_clean,
    }

def flatten_publication(pub: Dict[str, Any], user_obj_id: str) -> Dict[str, Any]:
    authors = "; ".join(a.get("fullName", "") for a in pub.get("authors", []))
    labels = "; ".join(l.get("value", "") for l in pub.get("labels", []))
    pd = pub.get("publicationDate", {})
    return {
        "userObjectId": user_obj_id,
        "publicationObjectId": pub.get("objectId", ""),
        "title": clean_text(pub.get("title", "")),
        "journal": pub.get("journal", ""),
        "doi": pub.get("doi", ""),
        "pubYear": pd.get("year", ""),
        "pubMonth": pd.get("month", ""),
        "pubDay": pd.get("day", ""),
        "volume": pub.get("volume", ""),
        "issue": pub.get("issue", ""),
        "pages": pub.get("pagination", ""),
        "issn": pub.get("issn", ""),
        "labels": labels,
        "authors": authors,
        "url": pub.get("url", ""),
    }

def flatten_grant(g: Dict[str, Any], uid: str) -> Dict[str, Any]:
    """Flatten a grant record into a single row."""
    # Extract dates from the nested date1 structure
    date1 = g.get("date1", {})
    start_date = date1.get("dateTime", "")  # This is the full ISO date
    if not start_date and date1.get("year"):
        # Construct date from year/month/day if dateTime not available
        year = date1.get("year", "")
        month = str(date1.get("month", "")).zfill(2)
        day = str(date1.get("day", "")).zfill(2)
        if year and month and day:
            start_date = f"{year}-{month}-{day}"
    
    return {
        "objectId": g.get("objectId", ""),
        "discoveryUrlId": g.get("discoveryUrlId", ""),
        "title": clean_text(g.get("title", "")),
        "description": clean_text(g.get("description", "")),
        "startDate": start_date,
        "endDate": "",  # API doesn't seem to provide end dates
        "status": g.get("objectTypeDisplayName", ""),
        "role": g.get("role", ""),
        "amount": g.get("amount", ""),
        "currency": g.get("currency", ""),
        "funder": g.get("funderName", ""),
        "grantNumber": g.get("grantNumber", ""),
        "userId": uid
    }

def flatten_teaching(act: Dict[str, Any], user_obj_id: str) -> Dict[str, Any]:
    d1 = act.get("date1", {})
    d2 = act.get("date2", {})
    return {
        "userObjectId": user_obj_id,
        "teachingActivityObjectId": act.get("objectId", ""),
        "type": act.get("objectTypeDisplayName", ""),
        "startYear": d1.get("year", ""),
        "startMonth": d1.get("month", ""),
        "startDay": d1.get("day", ""),
        "endYear": d2.get("year", ""),
        "endMonth": d2.get("month", ""),
        "endDay": d2.get("day", ""),
        "title": clean_text(act.get("title", "")),
        "url": act.get("url", ""),
    }

def process_scholar(disc_id: str):
    js = fetch_user_js(disc_id)
    if not js:
        print(f"  Error: Could not fetch user {disc_id}")
        return None
    profile = extract_profile(js)
    user_obj_id = profile["objectId"]
    pubs, grants, teaching = [], [], []
    for page in fetch_all_pages(
        PUBS_API_URL,
        lambda s: {
            "objectId": disc_id,
            "objectType": "user",
            "pagination": {"perPage": PER_PAGE_PUBS, "startFrom": s},
            "favouritesFirst": True,
            "sort": "dateDesc"
        },
        PER_PAGE_PUBS
    ):
        for pub in page:
            pubs.append(flatten_publication(pub, user_obj_id))
    for page in fetch_all_pages(
        GRANTS_API_URL,
        lambda s: {
            "objectId": disc_id,
            "objectType": "user",
            "pagination": {"perPage": PER_PAGE_GRANTS, "startFrom": s}
        },
        PER_PAGE_GRANTS
    ):
        for grant in page:
            grants.append(flatten_grant(grant, user_obj_id))
    for page in fetch_all_pages(
        TEACH_API_URL,
        lambda s: {
            "objectId": disc_id,
            "objectType": "user",
            "pagination": {"perPage": PER_PAGE_TEACHING, "startFrom": s}
        },
        PER_PAGE_TEACHING
    ):
        for activity in page:
            teaching.append(flatten_teaching(activity, user_obj_id))
    return {
        "profile": profile,
        "publications": pubs,
        "grants": grants,
        "teaching": teaching
    }

# ---- MAIN ---------------------------------------------------------------
def main():
    # Read faculty names from CSV
    faculty_names = []
    with open(INPUT_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            faculty_names.append(row['PI Name'])
    print(f"Loaded {len(faculty_names)} faculty names from {INPUT_CSV}")

    # Find discoveryUrlIds for all faculty
    disc_ids = []
    for name in faculty_names:
        # Use manual override if present
        if name in MANUAL_DISCOVERY_IDS:
            disc_id = MANUAL_DISCOVERY_IDS[name]
            print(f"Manual override: {name} → {disc_id}")
            disc_ids.append((name, disc_id))
            continue
        # Convert 'Last, First Middle' to 'First Middle Last'
        if "," in name:
            last, first = [part.strip() for part in name.split(",", 1)]
            search_name = f"{first} {last}"
        else:
            search_name = name
        disc_id = find_user_id(search_name)
        if disc_id:
            disc_ids.append((name, disc_id))
            print(f"Found {name} → {disc_id}")
        else:
            print(f"Not found: {name}")
    if not disc_ids:
        print("No matching users found.")
        return
    print(f"\nFound {len(disc_ids)} users. Fetching full data...")
    all_profiles, all_pubs, all_grants, all_teaching = [], [], [], []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(process_scholar, disc_id): (name, disc_id) for name, disc_id in disc_ids}
        for fut in as_completed(futures):
            result = fut.result()
            name, disc_id = futures[fut]
            if result:
                all_profiles.append(result["profile"])
                all_pubs.extend(result["publications"])
                all_grants.extend(result["grants"])
                all_teaching.extend(result["teaching"])
            else:
                print(f"  Error processing {name} ({disc_id})")
    # Write CSVs
    print(f"\nWriting {len(all_profiles)} profiles...")
    if all_profiles:
        with open(PROFILES_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(all_profiles[0].keys()))
            writer.writeheader()
            writer.writerows(all_profiles)
    print(f"Writing {len(all_pubs)} publications...")
    if all_pubs:
        with open(PUBLICATIONS_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(all_pubs[0].keys()))
            writer.writeheader()
            writer.writerows(all_pubs)
    print(f"Writing {len(all_grants)} grants...")
    if all_grants:
        with open(GRANTS_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "objectId", "discoveryUrlId", "title", "description", 
                "startDate", "endDate", "status", "role", "amount", 
                "currency", "funder", "grantNumber", "userId"
            ])
            writer.writeheader()
            writer.writerows(all_grants)
    print(f"Writing {len(all_teaching)} teaching activities...")
    if all_teaching:
        with open(TEACHING_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(all_teaching[0].keys()))
            writer.writeheader()
            writer.writerows(all_teaching)
    print("\nDone.")

if __name__ == "__main__":
    main() 