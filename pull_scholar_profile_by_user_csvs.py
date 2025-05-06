#!/usr/bin/env python3
# pull_scholar_profile_by_user_csvs.py

"""
Pull complete Scholars@UAB profile for a specified user,
including profile details, research interests, teaching summary,
publications, grants and teaching activities.
Example user ID: 3048 (Andrea Cherrington).
"""

import csv
import time
import requests
import unicodedata

# ---- CONFIG --------------------------------------------------------------
USER_ID           = 3048                       # numeric user ID
PER_PAGE_PUBS     = 25                         # publications per page
PER_PAGE_GRANTS   = 25                         # grants per page
PER_PAGE_TEACHING = 25                         # teaching activities per page
PAUSE             = 0.1                        # seconds between page fetches

USERS_API_BASE    = "https://scholars.uab.edu/api/users/{}"
PUBS_API_URL      = "https://scholars.uab.edu/api/publications/linkedTo"
GRANTS_API_URL    = "https://scholars.uab.edu/api/grants/linkedTo"
TEACH_API_URL     = "https://scholars.uab.edu/api/teachingActivities/linkedTo"

HEADERS = {
    "User-Agent":   "UAB-Profile-Scraper/1.2 (ccampos@uab.edu)",
    "Accept":       "application/json",
    "Content-Type": "application/json",
}

# ---- CLEANING HELPER -----------------------------------------------------
def clean_text(s: str) -> str:
    """Normalize unicode, replace mojibake and fancy punctuation, collapse whitespace."""
    if not isinstance(s, str):
        return ""
    t = unicodedata.normalize("NFKC", s)
    t = t.replace("‚Äì", "-")
    for orig, repl in [
        ("\u2013", "-"), ("\u2014", "-"),
        ("“", '"'), ("”", '"'),
        ("‘", "'"), ("’", "'"),
    ]:
        t = t.replace(orig, repl)
    return " ".join(t.split())

# ---- FETCH FUNCTIONS -----------------------------------------------------
def fetch_user_js(uid: int) -> dict:
    """Fetch user JSON profile by numeric ID."""
    resp = requests.get(USERS_API_BASE.format(uid), headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()

# ---- PROFILE EXTRACTION --------------------------------------------------
def extract_profile(js: dict) -> dict:
    """Extract and clean core profile fields, including research and teaching."""
    email = js.get("emailAddress", {}).get("address", "")
    orcid = js.get("orcid", "") or ""

    # departments and positions
    depts = [p.get("department","") for p in js.get("positions",[]) if p.get("department")]
    titles = [p.get("position","")   for p in js.get("positions",[]) if p.get("position")]
    for appt in js.get("institutionalAppointments", []):
        if appt.get("position"):
            titles.append(appt["position"])

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
        "objectId":          js.get("objectId", ""),
        "first":             js.get("firstName", ""),
        "last":              js.get("lastName", ""),
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
    """Generic pager: yields lists of JSON items until exhausted."""
    start = 0
    while True:
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

# ---- FLATTEN HELPERS -----------------------------------------------------
def flatten_publication(pub: dict, user_obj_id: str) -> dict:
    authors = "; ".join(a.get("fullName","") for a in pub.get("authors",[]))
    labels  = "; ".join(lbl.get("value","")   for lbl in pub.get("labels",[]))
    pd = pub.get("publicationDate", {})
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
    d = gr.get("date1", {})
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
    """Flatten one teaching activity record to CSV row."""
    d1 = act.get("date1", {})
    d2 = act.get("date2", {})
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
    # 1) Profile
    js = fetch_user_js(USER_ID)
    slug = js.get("discoveryUrlId", str(USER_ID))
    profile = extract_profile(js)
    prof_file = f"{slug}_profile.csv"
    with open(prof_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(profile.keys()))
        writer.writeheader()
        writer.writerow(profile)
    print(f"Wrote profile to {prof_file}")

    user_obj_id = profile["objectId"]

    # 2) Publications
    pubs_file = f"{slug}_publications.csv"
    sample_pub = flatten_publication({}, user_obj_id)
    with open(pubs_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(sample_pub.keys()))
        writer.writeheader()
        for page in fetch_all_pages(
            PUBS_API_URL,
            lambda s: {
                "objectId":       slug,
                "objectType":     "user",
                "pagination":     {"perPage": PER_PAGE_PUBS, "startFrom": s},
                "favouritesFirst": True,
                "sort":           "dateDesc"
            },
            PER_PAGE_PUBS
        ):
            for pub in page:
                writer.writerow(flatten_publication(pub, user_obj_id))
    print(f"Wrote publications to {pubs_file}")

    # 3) Grants
    grants_file = f"{slug}_grants.csv"
    sample_gr = flatten_grant({}, user_obj_id)
    with open(grants_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(sample_gr.keys()))
        writer.writeheader()
        for page in fetch_all_pages(
            GRANTS_API_URL,
            lambda s: {
                "objectId":   slug,
                "objectType": "user",
                "pagination": {"perPage": PER_PAGE_GRANTS, "startFrom": s}
            },
            PER_PAGE_GRANTS
        ):
            for grant in page:
                writer.writerow(flatten_grant(grant, user_obj_id))
    print(f"Wrote grants to {grants_file}")

    # 4) Teaching Activities
    teach_file = f"{slug}_teaching_activities.csv"
    sample_teach = flatten_teaching({}, user_obj_id)
    with open(teach_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(sample_teach.keys()))
        writer.writeheader()
        for page in fetch_all_pages(
            TEACH_API_URL,
            lambda s: {
                "objectId":   slug,
                "objectType": "user",
                "pagination": {"perPage": PER_PAGE_TEACHING, "startFrom": s}
            },
            PER_PAGE_TEACHING
        ):
            for act in page:
                writer.writerow(flatten_teaching(act, user_obj_id))
    print(f"Wrote teaching activities to {teach_file}")

if __name__ == "__main__":
    main()