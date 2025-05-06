#!/usr/bin/env python3
# pull_master_scholars_by_faculty_list.py

"""
Master script: Pull complete Scholars@UAB profiles, publications, grants,
and teaching activities for a list of faculty by name and write to four CSVs:
- profiles.csv
- publications.csv
- grants.csv
- teaching_activities.csv

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

from faculty_fullnames import faculty_fullnames

# ---- CONFIG --------------------------------------------------------------
BASE_URL             = "https://scholars.uab.edu"
API_USERS            = f"{BASE_URL}/api/users"
PUBS_API_URL         = f"{BASE_URL}/api/publications/linkedTo"
GRANTS_API_URL       = f"{BASE_URL}/api/grants/linkedTo"
TEACHING_API_URL     = f"{BASE_URL}/api/teachingActivities/linkedTo"

PER_PAGE_PUBS        = 50
PER_PAGE_GRANTS      = 50
PER_PAGE_TEACHING    = 50
PAUSE                = 0.1  # seconds between requests

API_HEADERS = {
    "Accept":       "application/json, text/html, */*",
    "Content-Type": "application/json",
    "User-Agent":   "Mozilla/5.0"
}

# ---- OUTPUT FILES & FIELDS -----------------------------------------------
PROFILES_CSV      = "profiles.csv"
PUBLICATIONS_CSV  = "publications.csv"
GRANTS_CSV        = "grants.csv"
TEACHING_CSV      = "teaching_activities.csv"

PROFILE_FIELDS    = [
    "objectId", "first", "last", "email", "orcid",
    "department", "positions", "bio", "researchInterests", "teachingSummary"
]
PUB_FIELDS        = [
    "userObjectId", "publicationObjectId", "title", "journal", "doi",
    "pubYear", "pubMonth", "pubDay", "volume", "issue", "pages", "issn",
    "labels", "authors"
]
GRANT_FIELDS      = [
    "userObjectId", "grantObjectId", "title", "funder",
    "awardType", "year", "month", "day", "labels"
]
TEACH_FIELDS      = [
    "userObjectId", "teachingActivityObjectId", "type",
    "startYear", "startMonth", "startDay",
    "endYear", "endMonth", "endDay",
    "title"
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
        ("“", '"'), ("”", '"'),
        ("‘", "'"), ("’", "'"),
    ]
    for orig, repl in subs:
        t = t.replace(orig, repl)
    # collapse spaces/newlines
    return " ".join(t.split())

# ---- FIND & FETCH --------------------------------------------------------
def find_disc_id(full_name: str) -> str:
    first, last = full_name.split()[0], full_name.split()[-1]
    payload = {"params": {"by": "text", "type": "user", "text": f"{first} {last}"}}
    r = session.post(API_USERS, json=payload, headers=API_HEADERS, timeout=15)
    r.raise_for_status()
    for u in r.json().get("resource", []):
        if (u.get("firstName","").lower() == first.lower() and
            u.get("lastName","").lower()  == last.lower()):
            return u.get("discoveryUrlId")
    return None

def fetch_user_js(disc_id: str) -> dict:
    r = session.get(f"{API_USERS}/{disc_id}", headers=API_HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()

# ---- PROFILE EXTRACTION --------------------------------------------------
def extract_profile(js: dict) -> dict:
    email = js.get("emailAddress",{}).get("address","")
    orcid = js.get("orcid","")
    depts = [p["department"] for p in js.get("positions",[]) if p.get("department")]
    titles= [p["position"]   for p in js.get("positions",[]) if p.get("position")]
    for appt in js.get("institutionalAppointments",[]):
        if appt.get("position"):
            titles.append(appt["position"])

    # clean long‐form fields
    bio_clean = clean_text(js.get("overview",""))
    teach_clean = clean_text(js.get("teachingSummary",""))

    # research interests
    raw_ri = js.get("researchInterests","")
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
        "objectId":          js.get("objectId",""),
        "first":             js.get("firstName",""),
        "last":              js.get("lastName",""),
        "email":             email,
        "orcid":             orcid,
        "department":        "; ".join(sorted(set(depts))),
        "positions":         "; ".join(sorted(set(titles))),
        "bio":               bio_clean,
        "researchInterests": "; ".join(research),
        "teachingSummary":   teach_clean,
    }

# ---- PAGING GENERATOR ----------------------------------------------------
def fetch_all_pages(url: str, payload_fn, per_page: int):
    start = 0
    while True:
        payload = payload_fn(start)
        r = session.post(url, json=payload, headers=API_HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        results = data.get("items") or data.get("resource") or []
        if not results:
            break
        yield results
        total = data.get("pagination",{}).get("total", 0)
        start += per_page
        if start >= total:
            break
        time.sleep(PAUSE)

# ---- FLATTEN HELPERS -----------------------------------------------------
def flatten_publication(pub: dict, user_obj_id: str) -> dict:
    authors = "; ".join(a.get("fullName","") for a in pub.get("authors",[]))
    labels  = "; ".join(lbl.get("value","")   for lbl in pub.get("labels",[]))
    pd      = pub.get("publicationDate",{})
    return {
        "userObjectId":        user_obj_id,
        "publicationObjectId": pub.get("objectId",""),
        "title":               clean_text(pub.get("title","")),
        "journal":             pub.get("journal",""),
        "doi":                 pub.get("doi",""),
        "pubYear":             pd.get("year",""),
        "pubMonth":            pd.get("month",""),
        "pubDay":              pd.get("day",""),
        "volume":              pub.get("volume",""),
        "issue":               pub.get("issue",""),
        "pages":               pub.get("pagination",""),
        "issn":                pub.get("issn",""),
        "labels":              labels,
        "authors":             authors,
    }

def flatten_grant(gr: dict, user_obj_id: str) -> dict:
    d      = gr.get("date1",{})
    labels = "; ".join(lbl.get("value","") for lbl in gr.get("labels",[]))
    return {
        "userObjectId":  user_obj_id,
        "grantObjectId": gr.get("objectId",""),
        "title":         clean_text(gr.get("title","")),
        "funder":        gr.get("funderName",""),
        "awardType":     gr.get("objectTypeDisplayName",""),
        "year":          d.get("year",""),
        "month":         d.get("month",""),
        "day":           d.get("day",""),
        "labels":        labels,
    }

def flatten_teaching(act: dict, user_obj_id: str) -> dict:
    d1 = act.get("date1",{})
    d2 = act.get("date2",{})
    return {
        "userObjectId":             user_obj_id,
        "teachingActivityObjectId": act.get("objectId",""),
        "type":                     act.get("objectTypeDisplayName",""),
        "startYear":                d1.get("year",""),
        "startMonth":               d1.get("month",""),
        "startDay":                 d1.get("day",""),
        "endYear":                  d2.get("year",""),
        "endMonth":                 d2.get("month",""),
        "endDay":                   d2.get("day",""),
        "title":                    clean_text(act.get("title","")),
    }

# ---- MAIN ---------------------------------------------------------------
def main():
    with open(PROFILES_CSV,     "w", newline="", encoding="utf-8") as pf, \
         open(PUBLICATIONS_CSV, "w", newline="", encoding="utf-8") as pbf, \
         open(GRANTS_CSV,       "w", newline="", encoding="utf-8") as gf, \
         open(TEACHING_CSV,     "w", newline="", encoding="utf-8") as tf:

        prof_writer   = csv.DictWriter(pf, fieldnames=PROFILE_FIELDS)
        pubs_writer   = csv.DictWriter(pbf, fieldnames=PUB_FIELDS)
        grants_writer = csv.DictWriter(gf, fieldnames=GRANT_FIELDS)
        teach_writer  = csv.DictWriter(tf, fieldnames=TEACH_FIELDS)

        prof_writer.writeheader()
        pubs_writer.writeheader()
        grants_writer.writeheader()
        teach_writer.writeheader()

        for full_name in faculty_fullnames:
            print(f"Processing {full_name}…")
            disc_id = find_disc_id(full_name)
            if not disc_id:
                print(f"  ❌ No discoveryUrlId for {full_name}")
                continue

            # Profile
            js = fetch_user_js(disc_id)
            profile = extract_profile(js)
            prof_writer.writerow(profile)
            uid = profile["objectId"]
            print(f"  ✅ Profile saved (ID {uid})")

            # Publications
            for page in fetch_all_pages(
                PUBS_API_URL,
                lambda s: {
                    "objectId":      disc_id,
                    "objectType":    "user",
                    "pagination":    {"perPage": PER_PAGE_PUBS, "startFrom": s},
                    "favouritesFirst": True,
                    "sort":          "dateDesc"
                },
                PER_PAGE_PUBS
            ):
                for pub in page:
                    pubs_writer.writerow(flatten_publication(pub, uid))

            # Grants
            for page in fetch_all_pages(
                GRANTS_API_URL,
                lambda s: {
                    "objectId":   disc_id,
                    "objectType": "user",
                    "pagination": {"perPage": PER_PAGE_GRANTS, "startFrom": s}
                },
                PER_PAGE_GRANTS
            ):
                for gr in page:
                    grants_writer.writerow(flatten_grant(gr, uid))

            # Teaching Activities
            for page in fetch_all_pages(
                TEACHING_API_URL,
                lambda s: {
                    "objectId":   disc_id,
                    "objectType": "user",
                    "pagination": {"perPage": PER_PAGE_TEACHING, "startFrom": s}
                },
                PER_PAGE_TEACHING
            ):
                for act in page:
                    teach_writer.writerow(flatten_teaching(act, uid))

    print("\nDone.")
    print(f"Wrote profiles           → {PROFILES_CSV}")
    print(f"Wrote publications       → {PUBLICATIONS_CSV}")
    print(f"Wrote grants             → {GRANTS_CSV}")
    print(f"Wrote teaching activities→ {TEACHING_CSV}")

if __name__ == "__main__":
    main()