#!/usr/bin/env python3
# pull_scholar_profile_by_user_csvs.py

"""
Pull complete Scholars@UAB profiles for a list of faculty members from a CSV file,
including profile details, research interests, teaching summary,
publications, grants and teaching activities.
"""

import csv
import time
import requests
import unicodedata
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import scholars_api_shim  # noqa: F401

# ---- CONFIG --------------------------------------------------------------
INPUT_CSV = "CDTR_MemberBase_Cleaned.csv"  # Input CSV file with faculty names
PER_PAGE_PUBS = 500                        # publications per page
PER_PAGE_GRANTS = 500                      # grants per page
PER_PAGE_TEACHING = 500                    # teaching activities per page
PAUSE = 0.1                               # seconds between page fetches

# Add timestamp to filenames
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

USERS_API_BASE = "https://scholars.uab.edu/api/users/{}"
USERS_API_SEARCH = "https://scholars.uab.edu/api/users"
PUBS_API_URL = "https://scholars.uab.edu/api/publications/linkedTo"
GRANTS_API_URL = "https://scholars.uab.edu/api/grants/linkedTo"
TEACH_API_URL = "https://scholars.uab.edu/api/teachingActivities/linkedTo"

HEADERS = {
    "User-Agent": "UAB-Scholars-Tool/1.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# ---- MANUAL OVERRIDES ---------------------------------------------------
# Map of 'PI Name' (as in CSV) to correct discoveryUrlId
MANUAL_DISCOVERY_IDS = {
    'Allen Watts, Kristen': '12139-kristen-allen-watts',
    'Cedillo, Yenni': '17388-yenni-cedillo-juarez',
    # Add more overrides here if needed
}

# ---- NAME SEARCH HELPERS -------------------------------------------------
def get_name_variations(full_name: str) -> List[Tuple[str, str]]:
    """Generate variations of a name for searching."""
    parts = full_name.split()
    if not parts:
        return []
    
    # Handle cases with middle names/initials
    if len(parts) > 2:
        # Try first + last
        variations = [(parts[0], parts[-1])]
        # Try first initial + last
        variations.append((parts[0][0], parts[-1]))
        # Try first + middle initial + last
        if len(parts) == 3:
            variations.append((parts[0], f"{parts[1][0]} {parts[2]}"))
        return variations
    
    # Simple first + last name
    return [(parts[0], parts[-1])]

def find_user_id(full_name: str) -> Optional[str]:
    """Find a user's ID using various name formats."""
    variations = get_name_variations(full_name)
    
    for first, last in variations:
        try:
            payload = {"params": {"by": "text", "type": "user", "text": f"{first} {last}"}}
            r = requests.post(USERS_API_SEARCH, json=payload, headers=HEADERS, timeout=15)
            r.raise_for_status()
            
            for u in r.json().get("resource", []):
                # Check if either the exact match or a close match
                if (u.get("firstName","").lower() == first.lower() and
                    u.get("lastName","").lower() == last.lower()):
                    return u.get("objectId")
                
                # Also check if the last name matches and first name is a variation
                if (u.get("lastName","").lower() == last.lower() and
                    (u.get("firstName","").lower().startswith(first.lower()) or
                     first.lower().startswith(u.get("firstName","").lower()))):
                    return u.get("objectId")
        except Exception as e:
            print(f"Error searching for {full_name}: {str(e)}")
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
def fetch_user_js(uid: int) -> Optional[Dict[str, Any]]:
    """Fetch user JSON profile by numeric ID."""
    try:
        resp = requests.get(USERS_API_BASE.format(uid), headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error fetching user {uid}: {str(e)}")
        return None

# ---- PROFILE EXTRACTION --------------------------------------------------
def extract_profile(js: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and clean core profile fields, including research and teaching."""
    email = js.get("emailAddress", {}).get("address", "")
    orcid = js.get("orcid", "") or ""

    # departments and positions
    depts = [p.get("department","").strip() for p in js.get("positions",[]) if p.get("department")]
    titles = [p.get("position","").strip() for p in js.get("positions",[]) if p.get("position")]
    for appt in js.get("institutionalAppointments", []):
        if appt.get("position"):
            titles.append(appt["position"].strip())

    # clean bio
    bio_clean = clean_text(js.get("overview", "").replace("\n", " "))

    # clean teaching summary
    teach_clean = clean_text(js.get("teachingSummary", "").replace("\n", " "))

    # research interests
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

# ---- PAGING GENERATOR ----------------------------------------------------
def fetch_all_pages(url: str, payload_fn, per_page: int):
    """Generic pager: yields lists of JSON items until exhausted."""
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
def flatten_publication(pub: Dict[str, Any], user_obj_id: str) -> Dict[str, Any]:
    """Map publication JSON to flat CSV row."""
    authors = "; ".join(a.get("fullName","") for a in pub.get("authors",[]))
    labels = "; ".join(l.get("value","") for l in pub.get("labels",[]))
    pd = pub.get("publicationDate", {})
    return {
        "userObjectId": user_obj_id,
        "publicationObjectId": pub.get("objectId",""),
        "title": clean_text(pub.get("title","")),
        "journal": pub.get("journal",""),
        "doi": pub.get("doi",""),
        "pubYear": pd.get("year",""),
        "pubMonth": pd.get("month",""),
        "pubDay": pd.get("day",""),
        "volume": pub.get("volume",""),
        "issue": pub.get("issue",""),
        "pages": pub.get("pagination",""),
        "issn": pub.get("issn",""),
        "labels": labels,
        "authors": authors,
        "url": pub.get("url",""),
    }

def flatten_grant(gr: Dict[str, Any], user_obj_id: str) -> Dict[str, Any]:
    """Map grant JSON to flat CSV row."""
    d1 = gr.get("date1", {})  # Start date
    d2 = gr.get("date2", {})  # End date
    labels = "; ".join(l.get("value","") for l in gr.get("labels",[]))
    return {
        "userObjectId": user_obj_id,
        "grantObjectId": gr.get("objectId",""),
        "title": clean_text(gr.get("title","")),
        "funder": gr.get("funderName",""),
        "awardType": gr.get("objectTypeDisplayName",""),
        "startYear": d1.get("year",""),
        "startMonth": d1.get("month",""),
        "startDay": d1.get("day",""),
        "endYear": d2.get("year",""),
        "endMonth": d2.get("month",""),
        "endDay": d2.get("day",""),
        "labels": labels,
        "url": gr.get("url",""),
    }

def flatten_teaching(act: Dict[str, Any], user_obj_id: str) -> Dict[str, Any]:
    """Flatten one teaching activity record to CSV row."""
    d1 = act.get("date1", {})
    d2 = act.get("date2", {})
    return {
        "userObjectId": user_obj_id,
        "teachingActivityObjectId": act.get("objectId",""),
        "type": act.get("objectTypeDisplayName",""),
        "startYear": d1.get("year",""),
        "startMonth": d1.get("month",""),
        "startDay": d1.get("day",""),
        "endYear": d2.get("year",""),
        "endMonth": d2.get("month",""),
        "endDay": d2.get("day",""),
        "title": clean_text(act.get("title","")),
        "url": act.get("url",""),
    }

def process_faculty_member(user_id: int, prof_writer, pubs_writer, grants_writer, teach_writer):
    """Process a single faculty member's data."""
    # 1) Profile
    js = fetch_user_js(user_id)
    if not js:
        print(f"Error: Could not fetch user {user_id}")
        return

    slug = js.get("discoveryUrlId", str(user_id))
    profile = extract_profile(js)
    prof_writer.writerow(profile)
    print(f"Processed profile for {profile['firstName']} {profile['lastName']}")

    user_obj_id = profile["objectId"]

    # 2) Publications
    for page in fetch_all_pages(
        PUBS_API_URL,
        lambda s: {
            "objectId": slug,
            "objectType": "user",
            "pagination": {"perPage": PER_PAGE_PUBS, "startFrom": s},
            "favouritesFirst": True,
            "sort": "dateDesc"
        },
        PER_PAGE_PUBS
    ):
        for pub in page:
            pubs_writer.writerow(flatten_publication(pub, user_obj_id))

    # 3) Grants
    for page in fetch_all_pages(
        GRANTS_API_URL,
        lambda s: {
            "objectId": slug,
            "objectType": "user",
            "pagination": {"perPage": PER_PAGE_GRANTS, "startFrom": s}
        },
        PER_PAGE_GRANTS
    ):
        for grant in page:
            grants_writer.writerow(flatten_grant(grant, user_obj_id))

    # 4) Teaching Activities
    for page in fetch_all_pages(
        TEACH_API_URL,
        lambda s: {
            "objectId": slug,
            "objectType": "user",
            "pagination": {"perPage": PER_PAGE_TEACHING, "startFrom": s}
        },
        PER_PAGE_TEACHING
    ):
        for activity in page:
            teach_writer.writerow(flatten_teaching(activity, user_obj_id))

# ---- MAIN ---------------------------------------------------------------
def main():
    # Create output files
    prof_file = f"profiles_{TIMESTAMP}.csv"
    pubs_file = f"publications_{TIMESTAMP}.csv"
    grants_file = f"grants_{TIMESTAMP}.csv"
    teach_file = f"teaching_activities_{TIMESTAMP}.csv"

    # Initialize CSV writers
    with open(prof_file, "w", newline="", encoding="utf-8") as f_prof, \
         open(pubs_file, "w", newline="", encoding="utf-8") as f_pubs, \
         open(grants_file, "w", newline="", encoding="utf-8") as f_grants, \
         open(teach_file, "w", newline="", encoding="utf-8") as f_teach:

        # Create sample records to get field names
        sample_prof = extract_profile({})
        sample_pub = flatten_publication({}, "")
        sample_gr = flatten_grant({}, "")
        sample_teach = flatten_teaching({}, "")

        # Initialize writers
        prof_writer = csv.DictWriter(f_prof, fieldnames=list(sample_prof.keys()))
        pubs_writer = csv.DictWriter(f_pubs, fieldnames=list(sample_pub.keys()))
        grants_writer = csv.DictWriter(f_grants, fieldnames=list(sample_gr.keys()))
        teach_writer = csv.DictWriter(f_teach, fieldnames=list(sample_teach.keys()))

        # Write headers
        prof_writer.writeheader()
        pubs_writer.writeheader()
        grants_writer.writeheader()
        teach_writer.writeheader()

        # Read faculty list from CSV
        with open(INPUT_CSV, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Extract faculty name and try to find their ID
                faculty_name = row['PI Name']
                print(f"\nProcessing faculty member: {faculty_name}")
                
                # Check for manual override first
                if faculty_name in MANUAL_DISCOVERY_IDS:
                    user_id = MANUAL_DISCOVERY_IDS[faculty_name]
                    print(f"Using manual override for {faculty_name}")
                else:
                    # Convert 'Last, First Middle' to 'First Middle Last'
                    if "," in faculty_name:
                        last, first = [part.strip() for part in faculty_name.split(",", 1)]
                        search_name = f"{first} {last}"
                    else:
                        search_name = faculty_name
                    
                    # Find the user ID for this faculty member
                    user_id = find_user_id(search_name)
                
                if user_id:
                    process_faculty_member(user_id, prof_writer, pubs_writer, grants_writer, teach_writer)
                else:
                    print(f"Could not find user ID for {faculty_name}")

    print(f"\nAll data has been written to:")
    print(f"- Profiles: {prof_file}")
    print(f"- Publications: {pubs_file}")
    print(f"- Grants: {grants_file}")
    print(f"- Teaching Activities: {teach_file}")

if __name__ == "__main__":
    main()