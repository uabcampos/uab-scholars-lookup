#!/usr/bin/env python3
# fetch_scholar.py
"""
FastAPI wrapper for public Scholars@UAB data.

Endpoints
──────────
• /fetch_profile_by_name
• /fetch_publications_by_name
• /fetch_grants_by_name
• /fetch_teaching_by_name
• /search_by_research_interest              (quick, sequential scan)
• /search_by_research_interest_chunked      (chunked / validated)
• /search_by_department_chunked             (NEW – threaded dept-scan)
• /fetch_scholar_by_name                    (combined snapshot)
"""

from __future__ import annotations

import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

import requests
from fastapi import Body, FastAPI, HTTPException
from pydantic import BaseModel, Field, conint

# ────────────────────── FastAPI app ────────────────────────────
app = FastAPI()

# ────────────────────── Configuration ──────────────────────────
BASE_URL          = "https://scholars.uab.edu"
API_USERS         = f"{BASE_URL}/api/users"
API_PUBS          = f"{BASE_URL}/api/publications/linkedTo"
API_GRANTS        = f"{BASE_URL}/api/grants/linkedTo"
API_TEACHING      = f"{BASE_URL}/api/teachingActivities/linkedTo"

SEARCH_PAGE_SIZE  = 500
PAUSE_SECONDS     = 0.1
MAX_UID           = 6000           # highest numeric /api/users/{id} to scan

HEADERS = {
    "Accept":       "application/json, text/html, */*",
    "Content-Type": "application/json",
    "User-Agent":   "UAB-Scholars-Tool/1.0",
}

session = requests.Session()

# ────────────────────── Pydantic models ────────────────────────
class BaseLookupRequest(BaseModel):
    faculty_name: str = Field(..., description="Full name as it appears in Scholars@UAB")

class PublicationLookupRequest(BaseLookupRequest):
    since_year: Optional[int] = Field(None, ge=1900)
    limit:      Optional[int] = Field(None, ge=1, le=500)

class GrantLookupRequest(BaseLookupRequest):
    since_year: Optional[int] = Field(None, ge=1900)
    limit:      Optional[int] = Field(None, ge=1, le=500)

class TeachingLookupRequest(BaseLookupRequest):
    since_year: Optional[int] = Field(None, ge=1900)
    limit:      Optional[int] = Field(None, ge=1, le=500)

class ResearchSearchRequest(BaseModel):
    search_term: str = Field(..., description="Substring to search for (case-insensitive)")
    max_results: int = Field(25, ge=1, le=500)

class DepartmentSearchRequest(BaseModel):
    department: str = Field(..., description="Primary department string")
    related_terms: Optional[List[str]] = Field(None, description="Aliases / sub-divisions")
    role_keywords: Optional[List[str]] = Field(None, description="Keywords within research interests")
    max_results: int = Field(25, ge=1, le=500)

class ResearchSearchChunkedRequest(BaseModel):
    search_terms: List[str]            = Field(..., min_items=1)
    chunk_size:  conint(ge=1, le=1000) = 500
    min_id:      conint(ge=1)          = 1
    max_id:      conint(ge=1)          = MAX_UID
    max_results: conint(ge=1, le=5000) = 1000

# ────────────────────── Helper functions ───────────────────────
def clean_text(s: str) -> str:
    if not isinstance(s, str):
        return ""
    t = unicodedata.normalize("NFKC", s).replace("‚Äì", "-")
    subs = [
        ("\u2013", "-"), ("\u2014", "-"),
        ("\u201c", '"'), ("\u201d", '"'),
        ("\u2018", "'"), ("\u2019", "'"),
    ]
    for a, b in subs:
        t = t.replace(a, b)
    return " ".join(t.split())

def get_name_variations(full_name: str) -> List[tuple[str, str]]:
    parts = full_name.split()
    first, last = parts[0], parts[-1]
    variations: List[tuple[str, str]] = [(first, last)]

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
        "Yu-Mei": "Yu Mei",
    }
    if full_name in name_map:
        alt = name_map[full_name].split()
        variations.append((alt[0], alt[-1]))
        if len(alt) > 2:
            variations.append((f"{alt[0]} {alt[1]}", alt[-1]))

    if "-" in full_name:
        nh = full_name.replace("-", " ").split()
        variations.append((nh[0], nh[-1]))
        if len(nh) > 2:
            variations.append((nh[0], f"{nh[-2]} {nh[-1]}"))

    if "Jr" in last or "Sr" in last:
        base = last.replace("Jr", "").replace("Sr", "").strip()
        variations += [(first, base), (first, f"{base}, Jr."), (first, f"{base}, Sr.")]
        if len(parts) > 2:
            mid = parts[1]
            variations += [
                (f"{first} {mid}", base),
                (f"{first} {mid}", f"{base}, Jr."),
                (f"{first} {mid}", f"{base}, Sr."),
            ]

    if len(parts) > 2 and len(parts[-2]) == 1:
        variations.append((f"{first} {parts[-2]}", last))

    return variations

def find_disc_id(full_name: str) -> Optional[str]:
    for first, last in get_name_variations(full_name):
        try:
            payload = {
                "params": {"by": "text", "category": "user", "text": f"{first} {last}"},
                "pagination": {"startFrom": 0, "perPage": 25},
            }
            r = session.post(API_USERS, json=payload, headers=HEADERS, timeout=15)
            r.raise_for_status()
            for u in r.json().get("resource", []):
                fn, ln = u.get("firstName", "").lower(), u.get("lastName", "").lower()
                if (fn == first.lower() and ln == last.lower()) or (
                    ln == last.lower() and (fn.startswith(first.lower()) or first.lower().startswith(fn))
                ):
                    # API now prefers numeric discoveryId for follow-up endpoints
                    return str(u.get("discoveryId") or u.get("objectId"))
        except Exception:
            continue
    return None

def fetch_user_js(identifier: str) -> Optional[Dict[str, Any]]:
    try:
        r = session.get(f"{API_USERS}/{identifier}", headers=HEADERS, timeout=15)
        r.raise_for_status()
        js = r.json()
        if isinstance(js, list):
            return js[0] if js else None
        if isinstance(js, dict) and "resource" in js:
            return js["resource"][0] if js["resource"] else None
        return js
    except Exception:
        return None

def fetch_all_pages(url: str, payload_fn, per_page: int):
    start = 0
    while True:
        try:
            r = session.post(url, json=payload_fn(start), headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
            items = data.get("items") or data.get("resource") or []
            if not items:
                break
            yield items
            start += per_page
            if start >= data.get("pagination", {}).get("total", 0):
                break
            time.sleep(PAUSE_SECONDS)
        except Exception:
            break

def flatten_publication(pub: Dict[str, Any], uid: str) -> Dict[str, Any]:
    authors = "; ".join(a.get("fullName", "") for a in pub.get("authors", []))
    labels  = "; ".join(l.get("value", "") for l in pub.get("labels", []))
    pd      = pub.get("publicationDate", {})
    return {
        "userObjectId":        uid,
        "publicationObjectId": pub.get("objectId", ""),
        "title":   clean_text(pub.get("title", "")),
        "journal": pub.get("journal", ""),
        "doi":     pub.get("doi", ""),
        "pubYear": pd.get("year", ""),
        "pubMonth": pd.get("month", ""),
        "pubDay":  pd.get("day", ""),
        "volume":  pub.get("volume", ""),
        "issue":   pub.get("issue", ""),
        "pages":   pub.get("pagination", ""),
        "issn":    pub.get("issn", ""),
        "labels":  labels,
        "authors": authors,
        "url":     pub.get("url", ""),
    }

def flatten_grant(gr: Dict[str, Any], uid: str) -> Dict[str, Any]:
    d = gr.get("date1", {})
    labels = "; ".join(l.get("value", "") for l in gr.get("labels", []))
    return {
        "userObjectId": uid,
        "grantObjectId": gr.get("objectId", ""),
        "title":      clean_text(gr.get("title", "")),
        "funder":     gr.get("funderName", ""),
        "awardType":  gr.get("objectTypeDisplayName", ""),
        "year":       d.get("year", ""),
        "month":      d.get("month", ""),
        "day":        d.get("day", ""),
        "labels":     labels,
        "url":        gr.get("url", ""),
    }

def flatten_teaching(act: Dict[str, Any], uid: str) -> Dict[str, Any]:
    d1, d2 = act.get("date1", {}), act.get("date2", {})
    return {
        "userObjectId": uid,
        "teachingActivityObjectId": act.get("objectId", ""),
        "type": act.get("objectTypeDisplayName", ""),
        "startYear": d1.get("year", ""), "startMonth": d1.get("month", ""), "startDay": d1.get("day", ""),
        "endYear":   d2.get("year", ""), "endMonth":   d2.get("month", ""), "endDay":   d2.get("day", ""),
        "title": clean_text(act.get("title", "")),
        "url":   act.get("url", ""),
    }

# ───────────────────────── Root ────────────────────────────────
@app.get("/")
def root():
    return {"message": "UAB Scholars helper API is running."}

# ───────────────────── Profile ────────────────────────────────
@app.post("/fetch_profile_by_name")
def fetch_profile_by_name(req: BaseLookupRequest):
    disc_id = find_disc_id(req.faculty_name)
    if not disc_id:
        raise HTTPException(404, "Faculty not found")
    js = fetch_user_js(disc_id)
    if not js:
        raise HTTPException(404, "Error fetching user data")

    def extract_ri(raw):
        if isinstance(raw, str):
            return clean_text(raw)
        return "; ".join(clean_text(x.get("value") or x.get("text") or "") for x in raw if isinstance(x, dict))

    profile = {
        "objectId":       js.get("objectId", ""),
        "discoveryUrlId": js.get("discoveryUrlId", ""),
        "firstName":      js.get("firstName", ""),
        "lastName":       js.get("lastName", ""),
        "email":          js.get("emailAddress", {}).get("address", ""),
        "orcid":          js.get("orcid", {}).get("value", js.get("orcid", "")),
        "department": "; ".join(p["department"].strip() for p in js.get("positions", []) if p.get("department")),
        "positions":  "; ".join(p["position"].strip() for p in js.get("positions", []) if p.get("position")),
        "bio":               clean_text(js.get("overview", "")),
        "researchInterests": extract_ri(js.get("researchInterests", "")),
        "teachingSummary":   clean_text(js.get("teachingSummary", "")),
    }
    return {"profile": profile}

# ─────────────────── Publications ─────────────────────────────
@app.post("/fetch_publications_by_name")
def fetch_publications_by_name(req: PublicationLookupRequest):
    disc_id = find_disc_id(req.faculty_name)
    if not disc_id:
        raise HTTPException(404, "Faculty not found")

    pubs, cnt = [], 0
    for page in fetch_all_pages(
        API_PUBS,
        lambda s: {
            "objectId": disc_id, "category": "user",
            "pagination": {"perPage": SEARCH_PAGE_SIZE, "startFrom": s},
            "favouritesFirst": True, "sort": "dateDesc",
        },
        SEARCH_PAGE_SIZE,
    ):
        for p in page:
            flat = flatten_publication(p, str(p.get("userObjectId", "")))
            if req.since_year and int(flat.get("pubYear") or 0) < req.since_year:
                continue
            pubs.append(flat); cnt += 1
            if req.limit and cnt >= req.limit:
                break
        if req.limit and cnt >= req.limit:
            break
    return {"publications": pubs}

# ───────────────────── Grants ────────────────────────────────
@app.post("/fetch_grants_by_name")
def fetch_grants_by_name(req: GrantLookupRequest):
    disc_id = find_disc_id(req.faculty_name)
    if not disc_id:
        raise HTTPException(404, "Faculty not found")

    grants, cnt = [], 0
    for page in fetch_all_pages(
        API_GRANTS,
        lambda s: {
            "objectId": disc_id, "category": "user",
            "pagination": {"perPage": SEARCH_PAGE_SIZE, "startFrom": s},
        },
        SEARCH_PAGE_SIZE,
    ):
        for g in page:
            flat = flatten_grant(g, str(g.get("userObjectId", "")))
            if req.since_year and int(flat.get("year") or 0) < req.since_year:
                continue
            grants.append(flat); cnt += 1
            if req.limit and cnt >= req.limit:
                break
        if req.limit and cnt >= req.limit:
            break
    return {"grants": grants}

# ─────────────────── Teaching ────────────────────────────────
@app.post("/fetch_teaching_by_name")
def fetch_teaching_by_name(req: TeachingLookupRequest):
    disc_id = find_disc_id(req.faculty_name)
    if not disc_id:
        raise HTTPException(404, "Faculty not found")

    acts, cnt = [], 0
    for page in fetch_all_pages(
        API_TEACHING,
        lambda s: {
            "objectId": disc_id, "category": "user",
            "pagination": {"perPage": SEARCH_PAGE_SIZE, "startFrom": s},
        },
        SEARCH_PAGE_SIZE,
    ):
        for t in page:
            flat = flatten_teaching(t, str(t.get("userObjectId", "")))
            if req.since_year and int(flat.get("startYear") or 0) < req.since_year:
                continue
            acts.append(flat); cnt += 1
            if req.limit and cnt >= req.limit:
                break
        if req.limit and cnt >= req.limit:
            break
    return {"teaching": acts}

# ───────────── Research-interest (quick) ──────────────────────
@app.post("/search_by_research_interest")
def search_by_research_interest(req: ResearchSearchRequest):
    term = req.search_term.lower()
    results: List[Dict[str, Any]] = []
    uid = 1
    while uid <= MAX_UID and len(results) < req.max_results:
        js = fetch_user_js(str(uid))
        if js:
            raw = js.get("researchInterests", "")
            pool = (
                [raw] if isinstance(raw, str) else
                [x.get("value") or x.get("text") or "" for x in raw if isinstance(x, dict)]
            )
            if any(term in p.lower() for p in pool):
                results.append({
                    "objectId": js["objectId"],
                    "discoveryUrlId": js["discoveryUrlId"],
                    "firstName": js["firstName"],
                    "lastName": js["lastName"],
                })
        uid += 1
    return {"matches": results}

# ─────── Research-interest (chunked)  ─────────────────────────
@app.post("/search_by_research_interest_chunked")
def search_by_research_interest_chunked(req: ResearchSearchChunkedRequest):
    terms = [t.lower() for t in req.search_terms]
    matches: List[Dict[str, Any]] = []
    uid = req.min_id
    while uid <= req.max_id and len(matches) < req.max_results:
        chunk_end = min(uid + req.chunk_size - 1, req.max_id)
        for user_id in range(uid, chunk_end + 1):
            js = fetch_user_js(str(user_id))
            if not js:
                continue
            raw = js.get("researchInterests", "")
            pool: List[str] = (
                [raw] if isinstance(raw, str) else
                [clean_text(x.get("value") or x.get("text") or "") for x in raw if isinstance(x, dict)]
            )
            joined = " ".join(pool).lower()
            if any(t in joined for t in terms):
                matches.append({
                    "objectId": js["objectId"],
                    "discoveryUrlId": js["discoveryUrlId"],
                    "firstName": js["firstName"],
                    "lastName": js["lastName"],
                    "email": js.get("emailAddress", {}).get("address", ""),
                })
                if len(matches) >= req.max_results:
                    break
        uid = chunk_end + 1
    return {"matches": matches, "count": len(matches)}

# ─────────── Department (chunked, threaded) ───────────────────
@app.post("/search_by_department_chunked")
def search_by_department_chunked(req: DepartmentSearchRequest):
    dept_terms = [req.department.lower()] + [t.lower() for t in (req.related_terms or [])]
    role_kw    = [k.lower() for k in (req.role_keywords or [])]

    def check_uid(uid: int) -> Optional[Dict[str, Any]]:
        js = fetch_user_js(str(uid))
        if not js:
            return None
        # direct department match
        for p in js.get("positions", []):
            dept = (p.get("department") or "").lower()
            if any(term in dept for term in dept_terms):
                return js
        # role keywords fallback
        if role_kw:
            ri_raw = js.get("researchInterests", "")
            ri_text = (
                ri_raw.lower() if isinstance(ri_raw, str) else
                " ".join((x.get("value") or x.get("text") or "").lower() for x in ri_raw if isinstance(x, dict))
            )
            if any(k in ri_text for k in role_kw):
                return js
        return None

    matches: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(check_uid, i): i for i in range(1, MAX_UID + 1)}
        for fut in as_completed(futures):
            js = fut.result()
            if js:
                matches.append({
                    "objectId": js["objectId"],
                    "discoveryUrlId": js["discoveryUrlId"],
                    "firstName": js["firstName"],
                    "lastName": js["lastName"],
                    "email": js.get("emailAddress", {}).get("address", ""),
                    "department": "; ".join(
                        p["department"].strip()
                        for p in js.get("positions", []) if p.get("department")
                    ),
                })
            if len(matches) >= req.max_results:
                break

    return {"matches": matches, "count": len(matches)}

# ─────────── Combined snapshot (capped) ───────────────────────
@app.post("/fetch_scholar_by_name")
def fetch_scholar_by_name(req: BaseLookupRequest):
    disc_id = find_disc_id(req.faculty_name)
    if not disc_id:
        raise HTTPException(404, "Faculty not found")
    js = fetch_user_js(disc_id)
    if not js:
        raise HTTPException(404, "Error fetching user data")

    profile = {
        "objectId": js["objectId"],
        "discoveryUrlId": js["discoveryUrlId"],
        "firstName": js["firstName"],
        "lastName": js["lastName"],
        "email": js.get("emailAddress", {}).get("address", ""),
        "department": "; ".join(p["department"].strip() for p in js.get("positions", []) if p.get("department")),
        "positions":  "; ".join(p["position"].strip() for p in js.get("positions", []) if p.get("position")),
        "bio": clean_text(js.get("overview", "")),
        "researchInterests": (
            clean_text(js.get("researchInterests", ""))
            if isinstance(js.get("researchInterests"), str)
            else "; ".join(clean_text(x.get("value") or x.get("text") or "")
                           for x in js.get("researchInterests", []) if isinstance(x, dict))
        ),
        "teachingSummary": clean_text(js.get("teachingSummary", "")),
    }

    def first_n(pages, flat_fn, n=50):
        out, cnt = [], 0
        for page in pages:
            for item in page:
                out.append(flat_fn(item, str(item.get("userObjectId", ""))))
                cnt += 1
                if cnt >= n:
                    break
            if cnt >= n:
                break
        return out

    pubs = first_n(
        fetch_all_pages(
            API_PUBS,
            lambda s: {"objectId": disc_id, "category": "user",
                       "pagination": {"perPage": SEARCH_PAGE_SIZE, "startFrom": s},
                       "favouritesFirst": True, "sort": "dateDesc"},
            SEARCH_PAGE_SIZE,
        ), flatten_publication)

    grants = first_n(
        fetch_all_pages(
            API_GRANTS,
            lambda s: {"objectId": disc_id, "category": "user",
                       "pagination": {"perPage": SEARCH_PAGE_SIZE, "startFrom": s}},
            SEARCH_PAGE_SIZE,
        ), flatten_grant)

    teaching = first_n(
        fetch_all_pages(
            API_TEACHING,
            lambda s: {"objectId": disc_id, "category": "user",
                       "pagination": {"perPage": SEARCH_PAGE_SIZE, "startFrom": s}},
            SEARCH_PAGE_SIZE,
        ), flatten_teaching)

    return {"profile": profile, "publications": pubs, "grants": grants, "teaching": teaching}