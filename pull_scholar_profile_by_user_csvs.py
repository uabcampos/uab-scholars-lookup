#!/usr/bin/env python3
# pull_scholar_profile_by_user_csvs.py

"""
Pull complete Scholars@UAB profile for a specified user,
including profile details, research interests, teaching summary,
publications, and grants. Example user: Andrea Cherrington (450).
"""

import csv
import time
import requests
import unicodedata

# ---- CONFIG --------------------------------------------------------------
USER_ID           = 3048                       # numeric user ID
PER_PAGE_PUBS     = 25                         # publications per page
PER_PAGE_GRANTS   = 25                         # grants per page
PAUSE             = 0.1                        # seconds between page fetches

USERS_API_BASE    = "https://scholars.uab.edu/api/users/{}"
PUBS_API_URL      = "https://scholars.uab.edu/api/publications/linkedTo"
GRANTS_API_URL    = "https://scholars.uab.edu/api/grants/linkedTo"

HEADERS           = {
    "User-Agent":      "UAB-Profile-Scraper/1.2 (ccampos@uab.edu)",
    "Accept":          "application/json",
    "Content-Type":    "application/json",
}

# ---- CLEANING HELPER -----------------------------------------------------
def clean_text(s: str) -> str:
    """
    Normalize unicode to NFKC, replace mojibake and fancy punctuation,
    collapse whitespace, and return plain ASCII text.
    """
    if not isinstance(s, str):
        return ""
    t = unicodedata.normalize("NFKC", s)
    t = t.replace("‚Äì", "-")  # mojibake hyphen
    for orig, repl in [
        ("\u2013", "-"), ("\u2014", "-"),  # en/em dashes
        ("“", '"'), ("”", '"'),             # curly double quotes
        ("‘", "'"), ("’", "'"),             # curly single quotes
    ]:
        t = t.replace(orig, repl)
    return " ".join(t.split())

# ---- FETCH & FIND --------------------------------------------------------
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
    bio_raw = js.get("overview", "")
    bio_clean = clean_text(bio_raw.replace("\n", " "))

    # clean teaching summary
    teach_raw = js.get("teachingSummary", "")
    teach_clean = clean_text(teach_raw.replace("\n", " "))

    # research interests (string or list)
    raw_ri = js.get("researchInterests", "")
    research: list[str] = []
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
        r = requests.post(url, json=payload, headers=HEADERS, timeout=30)
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

# ---- FLATTEN HELPERS -----------------------------------------------------
def flatten_publication(pub: dict, user_obj_id: str) -> dict:
    """Flatten one publication record to a CSV-ready dict."""
    authors = "; ".join(a.get("fullName","") for a in pub.get("authors",[]))
    labels  = "; ".join(lbl.get("value","")    for lbl in pub.get("labels",[]))
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

def flatten_grant(grant: dict, user_obj_id: str) -> dict:
    """Flatten one grant record to a CSV-ready dict."""
    d = grant.get("date1", {})
    labels = "; ".join(lbl.get("value","") for lbl in grant.get("labels",[]))
    return {
        "userObjectId":  user_obj_id,
        "grantObjectId": grant.get("objectId",""),
        "title":         clean_text(grant.get("title","")),
        "funder":        grant.get("funderName",""),
        "awardType":     grant.get("objectTypeDisplayName",""),
        "year":          d.get("year",""),
        "month":         d.get("month",""),
        "day":           d.get("day",""),
        "labels":        labels,
    }

# ---- MAIN ---------------------------------------------------------------
def main():
    # 1) Profile CSV
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

    # 2) Publications CSV
    pubs_file = f"{slug}_publications.csv"
    sample_pub = flatten_publication({}, user_obj_id)
    with open(pubs_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(sample_pub.keys()))
        writer.writeheader()
        for page in fetch_all_pages(
            PUBS_API_URL,
            lambda start: {
                "objectId":       slug,
                "objectType":     "user",
                "pagination":     {"perPage": PER_PAGE_PUBS,   "startFrom": start},
                "favouritesFirst": True,
                "sort":           "dateDesc"
            },
            PER_PAGE_PUBS
        ):
            for pub in page:
                writer.writerow(flatten_publication(pub, user_obj_id))
    print(f"Wrote publications to {pubs_file}")

    # 3) Grants CSV
    grants_file = f"{slug}_grants.csv"
    sample_gr = flatten_grant({}, user_obj_id)
    with open(grants_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(sample_gr.keys()))
        writer.writeheader()
        for page in fetch_all_pages(
            GRANTS_API_URL,
            lambda start: {
                "objectId":   slug,
                "objectType": "user",
                "pagination": {"perPage": PER_PAGE_GRANTS, "startFrom": start}
            },
            PER_PAGE_GRANTS
        ):
            for grant in page:
                writer.writerow(flatten_grant(grant, user_obj_id))
    print(f"Wrote grants to {grants_file}")

if __name__ == "__main__":
    main()