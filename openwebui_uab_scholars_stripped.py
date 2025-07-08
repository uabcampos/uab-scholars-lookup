from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

import copy
import requests
from pydantic import BaseModel, Field

                                                                             
                                                           
                                                                             

_ORIG_POST = requests.Session.post                              
_ORIG_REQ_POST = requests.post                              

def _transform_payload(obj: Any) -> None:
                                                                        
    if isinstance(obj, dict):
        if "objectType" in obj and "category" not in obj:
            obj["category"] = obj.pop("objectType")
        if "type" in obj and "category" not in obj:
            obj["category"] = obj.pop("type")
        if "object" in obj and "category" not in obj:
            obj["category"] = obj.pop("object")

                                                          
        if "params" in obj and isinstance(obj["params"], dict):
            if obj["params"].get("by") == "text" and obj["params"].get("category") == "user":
                obj.setdefault("pagination", {"startFrom": 0, "perPage": 25})

        for v in obj.values():
            _transform_payload(v)
    elif isinstance(obj, list):
        for item in obj:
            _transform_payload(item)


def _patched_post(self_or_url, url: str | None = None, *args, **kw):
                                                                                  
    is_session = isinstance(self_or_url, requests.Session)
    sess = self_or_url if is_session else None
    dest = url if is_session else self_or_url                        

    if "json" in kw and isinstance(kw["json"], (dict, list)):
        js_copy = copy.deepcopy(kw["json"])
        _transform_payload(js_copy)
        kw["json"] = js_copy

    if is_session:
        return _ORIG_POST(sess, dest, *args, **kw)
    return _ORIG_REQ_POST(dest, *args, **kw)

                   
if not getattr(requests, "_uab_inline_patch", False):
    requests.Session.post = _patched_post                            
    requests.post = _patched_post                            
    requests._uab_inline_patch = True

BASE = "https://scholars.uab.edu/api"
HDRS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (OpenWebUI-UAB-Scholars)",
    "Content-Type": "application/json",
}

                                                            
MAIN_FORMAT = (
    """
<interpreter_output>
    <description>{description}</description>
    <output>{output}</output>
</interpreter_output>
"""
)

                         
import logging


def _setup_logger():
    name = "UABScholarsTool"
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logger.addHandler(h)
        logger.propagate = False
    return logger


logger = _setup_logger()

                                                                             
                                                                      
                                                                             

class NameLookup(BaseModel):
                                                                               

    faculty_name: str = Field(..., description="Full name, e.g. 'Andrea Cherrington'")
    include_publications: bool = Field(True, description="Include publication list")
    include_grants: bool = Field(False, description="Include grant list")
    include_teaching: bool = Field(False, description="Include teaching activities")
    max_items: int = Field(25, description="Maximum entries to pull for each list")


class DepartmentSearch(BaseModel):
                                                             

    department: str = Field(..., description="Department name substring, e.g. 'Preventive Medicine'")
    max_results: int = Field(10, description="Stop after this many matches (pagination continues under the hood)")


class PublicationsOnly(BaseModel):
                                                                               

    scholar_id: str = Field(..., description="Numeric discoveryId or discoveryUrlId slug")
    max_items: int = Field(50, description="How many publications to return")


                                                                             
              
                                                                             

def _post(url: str, payload: Dict[str, Any], timeout: int = 15) -> Dict[str, Any]:
                                                                                    
    r = requests.post(url, json=payload, headers=HDRS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _name_variations(name: str):
    name = name.replace(".", " ")
    parts = name.split()
    if len(parts) >= 2:
        first, last = parts[0], parts[-1]
        yield f"{first} {last}"
        yield f"{first[0]} {last}"
        yield last
    yield name


_ID_CACHE: Dict[str, str] = {}

def _find_numeric_id(full_name: str) -> Optional[str]:
    payload = {"params": {"by": "text", "category": "user", "text": full_name}, "pagination": {"startFrom": 0, "perPage": 25}}
    data = _post(f"{BASE}/users", payload)

    def _norm(n: str) -> str:
        return " ".join(n.lower().split())

    target = _norm(full_name)
    exact, loose = [], []
    for item in data.get("resource", []):
        full = _norm(f"{item.get('firstName','')} {item.get('lastName','')}")
        if full == target:
            exact.append(item)
        elif target in full or full in target:
            loose.append(item)

    chosen = None
    if exact:
        chosen = sorted(exact, key=lambda x: int(x.get("discoveryId", 1e9)))[0]
    elif loose:
        chosen = sorted(loose, key=lambda x: int(x.get("discoveryId", 1e9)))[0]
    elif data.get("resource"):
        chosen = data["resource"][0]

    if chosen:
        return str(chosen.get("discoveryId") or chosen.get("objectId"))
    return None


                                                                             
                                                      
                                                                             

def fetch_profile_by_name(params: NameLookup) -> Dict[str, Any]:              
                                                                                
    disc_id = _find_numeric_id(params.faculty_name)
    if disc_id:
        _ID_CACHE[params.faculty_name.strip().lower()] = disc_id
    if disc_id is None:
        return {"status": "not_found", "message": "Scholar not found"}

    profile = requests.get(f"{BASE}/users/{disc_id}", headers=HDRS, timeout=15).json()

    out: Dict[str, Any] = {
        "status": "ok",
        "profile": {
            "id": disc_id,
            "name": f"{profile.get('firstName', '')} {profile.get('lastName', '')}",
            "email": profile.get("emailAddress", {}).get("address"),
            "department": "; ".join(
                p.get("department", "") for p in profile.get("positions", []) if p.get("department")
            ),
            "positions": "; ".join(
                p.get("position", "") for p in profile.get("positions", []) if p.get("position")
            ),
            "bio": profile.get("overview", ""),
            "url": f"https://scholars.uab.edu/{profile.get('discoveryUrlId', disc_id)}",
        }
    }

    if params.include_publications:
        out["publications"] = _get_publications(disc_id, params.max_items)
    if params.include_grants:
        out["grants"] = _get_grants(disc_id, params.max_items)
    if params.include_teaching:
        out["teachingActivities"] = _get_teaching(disc_id, params.max_items)
    return out


def search_department(params: DepartmentSearch) -> Dict[str, Any]:
                                                          
    matches: List[Dict[str, Any]] = []
    start = 0
    per_page = 100
    while len(matches) < params.max_results:
        payload = {
            "params": {"by": "text", "category": "user", "text": params.department},
            "pagination": {"startFrom": start, "perPage": per_page},
        }
        data = _post(f"{BASE}/users", payload)
        for item in data.get("resource", []):
            positions = item.get("positions", [])
            if any(
                params.department.lower() in (p.get("department", "") or "").lower()
                for p in positions
            ):
                matches.append(
                    {
                        "id": item.get("discoveryId"),
                        "name": f"{item.get('firstName','')} {item.get('lastName','')}",
                        "department": "; ".join(p.get("department", "") for p in positions if p.get("department")),
                        "url": f"https://scholars.uab.edu/{item.get('discoveryUrlId')}",
                    }
                )
                if len(matches) >= params.max_results:
                    break
        if start + per_page >= data.get("pagination", {}).get("total", 0):
            break
        start += per_page
        time.sleep(0.1)
    return {"status": "ok", "results": matches}


def list_publications(params: PublicationsOnly) -> Dict[str, Any]:
                                                                               
    pubs = _get_publications(params.scholar_id, params.max_items)
    return {"status": "ok", "scholarId": params.scholar_id, "publications": pubs}


                                                                             
                        
                                                                             

def _get_publications(disc_id: str, limit: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    start, per_page = 0, 50
    while len(out) < limit:
        payload = {
            "objectId": disc_id,
            "category": "user",
            "pagination": {"startFrom": start, "perPage": per_page},
            "sort": "dateDesc",
        }
        data = _post(f"{BASE}/publications/linkedTo", payload)
        for pub in data.get("resource", []):
            link_field = pub.get("url")
            if link_field and link_field.startswith("http"):
                link = link_field
            elif pub.get("doi"):
                link = f"https://doi.org/{pub['doi']}"
            else:
                link = None
            out.append({
                "title": pub.get("title"),
                "year": pub.get("publicationDate", {}).get("year"),
                "journal": pub.get("journal"),
                "doi": pub.get("doi"),
                "url": link,
            })
            if len(out) >= limit:
                break
        if start + per_page >= data.get("pagination", {}).get("total", 0):
            break
        start += per_page
    return out


def _get_grants(disc_id: str, limit: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    start, per_page = 0, 50
    while len(out) < limit:
        payload = {
            "objectId": disc_id,
            "category": "user",
            "pagination": {"startFrom": start, "perPage": per_page},
        }
        data = _post(f"{BASE}/grants/linkedTo", payload)
        for g in data.get("resource", []):
            out.append(
                {
                    "title": g.get("title"),
                    "funder": g.get("funderName"),
                    "awardType": g.get("objectTypeDisplayName"),
                    "year": g.get("date1", {}).get("year"),
                }
            )
            if len(out) >= limit:
                break
        if start + per_page >= data.get("pagination", {}).get("total", 0):
            break
        start += per_page
    return out


def _get_teaching(disc_id: str, limit: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    start, per_page = 0, 100
    while len(out) < limit:
        payload = {
            "objectId": disc_id,
            "category": "user",
            "pagination": {"startFrom": start, "perPage": per_page},
        }
        data = _post(f"{BASE}/teachingActivities/linkedTo", payload)
        out.extend(
            {
                "title": t.get("title"),
                "startYear": t.get("date1", {}).get("year"),
            }
            for t in data.get("resource", [])
        )
        if start + per_page >= data.get("pagination", {}).get("total", 0):
            break
        start += per_page
    return out


# ---------------------------------------------------------------------------
# Backward-compatibility convenience: quick lookup by name (no extras)
# ---------------------------------------------------------------------------


def search_by_name(faculty_name: str) -> Dict[str, Any]:
    """Return a minimal profile block (no pubs/grants) for *faculty_name*."""
    disc_id = _find_numeric_id(faculty_name)
    if disc_id is None:
        return {"status": "not_found", "message": "Scholar not found"}

    profile = requests.get(f"{BASE}/users/{disc_id}", headers=HDRS, timeout=15).json()
    return {
        "status": "ok",
        "firstName": profile.get("firstName"),
        "lastName": profile.get("lastName"),
        "discoveryUrlId": profile.get("discoveryUrlId", f"{disc_id}-{profile.get('firstName','').lower()}-{profile.get('lastName','').lower()}").lower(),
        "position": "; ".join(p.get("position", "") for p in profile.get("positions", []) if p.get("position")),
        "department": "; ".join(p.get("department", "") for p in profile.get("positions", []) if p.get("department")),
        "profileUrl": f"https://scholars.uab.edu/{profile.get('discoveryUrlId', disc_id)}",
    }


__all__ = [
    "fetch_profile_by_name",
    "search_department",
    "list_publications",
    "search_by_name",
]

                                                                             
                                                                         
                                                                             

class Tools:                                                           
\
\
\
\
\
\
\
\
\
\
\
       

    def fetch_profile_by_name(self, params):                            
        if isinstance(params, dict):
            params = NameLookup(**params)
        data = fetch_profile_by_name(params)
        return MAIN_FORMAT.format(
            description=f"Profile for {params.faculty_name} (publications={params.include_publications}, grants={params.include_grants})",
            output=json.dumps(data, ensure_ascii=False),
        )

    def search_department(self, params):                            
        if isinstance(params, dict):
            params = DepartmentSearch(**params)
        data = search_department(params)
        return MAIN_FORMAT.format(
            description=f"Department search for '{params.department}'",
            output=json.dumps(data, ensure_ascii=False),
        )

    def list_publications(self, params):                            
        if isinstance(params, dict):
            params = PublicationsOnly(**params)
        data = list_publications(params)
        return MAIN_FORMAT.format(
            description=f"Publications for scholar {params.scholar_id}",
            output=json.dumps(data, ensure_ascii=False),
        )

    # ------------------------------------------------------------------
    # Compatibility method: search_by_name
    # ------------------------------------------------------------------

    def search_by_name(self, faculty_name: str):  # type: ignore[valid-type]
        data = search_by_name(faculty_name)
        return MAIN_FORMAT.format(
            description=f"Quick lookup for {faculty_name}",
            output=json.dumps(data, ensure_ascii=False),
        ) 