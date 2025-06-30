"""openwebui_uab_scholars
A lightweight set of helper functions that expose the UAB Scholars API to
Open WebUI (or any LLM runtime that supports the OpenAI-functions style
schema extraction).

Each public function is synchronous (to avoid extra event-loop setup) and
returns plain Python data structures which are directly serialisable to
JSON.

All API pecularities discovered in June-2025 are handled:
• key renamed    – "category" instead of the legacy "type"/"objectType"/"object"
• pagination req – every /api/users query must include a pagination block
• numeric IDs    – linked-endpoint calls expect the numeric discoveryId

Dependencies:
    pip install requests pydantic
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

import copy
import requests
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Minimal inline shim (replaces external scholars_api_shim)
# ---------------------------------------------------------------------------

_ORIG_POST = requests.Session.post  # save original bound method
_ORIG_REQ_POST = requests.post      # save original function

def _transform_payload(obj: Any) -> None:
    """Recursively convert legacy keys and inject default pagination."""
    if isinstance(obj, dict):
        if "objectType" in obj and "category" not in obj:
            obj["category"] = obj.pop("objectType")
        if "type" in obj and "category" not in obj:
            obj["category"] = obj.pop("type")
        if "object" in obj and "category" not in obj:
            obj["category"] = obj.pop("object")

        # auto-pagination for /api/users queries if absent
        if "params" in obj and isinstance(obj["params"], dict):
            if obj["params"].get("by") == "text" and obj["params"].get("category") == "user":
                obj.setdefault("pagination", {"startFrom": 0, "perPage": 25})

        for v in obj.values():
            _transform_payload(v)
    elif isinstance(obj, list):
        for item in obj:
            _transform_payload(item)


def _patched_post(self_or_url, url: str | None = None, *args, **kw):
    """Wrapper around requests.post / Session.post that applies transformation."""
    is_session = isinstance(self_or_url, requests.Session)
    sess = self_or_url if is_session else None
    dest = url if is_session else self_or_url  # positional semantics

    if "json" in kw and isinstance(kw["json"], (dict, list)):
        js_copy = copy.deepcopy(kw["json"])
        _transform_payload(js_copy)
        kw["json"] = js_copy

    if is_session:
        return _ORIG_POST(sess, dest, *args, **kw)
    return _ORIG_REQ_POST(dest, *args, **kw)

# Monkey-patch once
if not getattr(requests, "_uab_inline_patch", False):
    requests.Session.post = _patched_post  # type: ignore[assignment]
    requests.post = _patched_post  # type: ignore[assignment]
    requests._uab_inline_patch = True

BASE = "https://scholars.uab.edu/api"
HDRS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (OpenWebUI-UAB-Scholars)",
    "Content-Type": "application/json",
}

# ---------------------------------------------------------------------------
# Pydantic models (input validation + automatic JSON schema for WebUI)
# ---------------------------------------------------------------------------

class NameLookup(BaseModel):
    """Lookup a scholar profile (and optionally related items) by full name."""

    faculty_name: str = Field(..., description="Full name, e.g. 'Andrea Cherrington'")
    include_publications: bool = Field(True, description="Include publication list")
    include_grants: bool = Field(False, description="Include grant list")
    include_teaching: bool = Field(False, description="Include teaching activities")
    max_items: int = Field(25, description="Maximum entries to pull for each list")


class DepartmentSearch(BaseModel):
    """Find all scholars in a department (quick overview)."""

    department: str = Field(..., description="Department name substring, e.g. 'Preventive Medicine'")
    max_results: int = Field(10, description="Stop after this many matches (pagination continues under the hood)")


class PublicationsOnly(BaseModel):
    """Return only publications for a scholar (numeric discoveryId or slug)."""

    scholar_id: str = Field(..., description="Numeric discoveryId or discoveryUrlId slug")
    max_items: int = Field(50, description="How many publications to return")


# ---------------------------------------------------------------------------
# Helper layer
# ---------------------------------------------------------------------------

def _post(url: str, payload: Dict[str, Any], timeout: int = 15) -> Dict[str, Any]:
    """Wrapper around POST that raises for HTTP != 200 and JSON-decodes the body."""
    r = requests.post(url, json=payload, headers=HDRS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _find_numeric_id(full_name: str) -> Optional[str]:
    """Return numeric discoveryId (as string) for the first exact match of *full_name*."""
    payload = {
        "params": {"by": "text", "category": "user", "text": full_name},
        "pagination": {"startFrom": 0, "perPage": 25},
    }
    data = _post(f"{BASE}/users", payload)
    for item in data.get("resource", []):
        if (
            item.get("firstName", "").lower() + " " + item.get("lastName", "").lower()
            == full_name.lower()
        ):
            return str(item.get("discoveryId") or item.get("objectId"))
    # fall-back: first result at all
    if data.get("resource"):
        it = data["resource"][0]
        return str(it.get("discoveryId") or it.get("objectId"))
    return None


# ---------------------------------------------------------------------------
# Public-facing functions (auto-exposed by Open WebUI)
# ---------------------------------------------------------------------------

def fetch_profile_by_name(params: NameLookup) -> Dict[str, Any]:  # noqa: D401
    """Fetch a scholar profile and optionally publications, grants, teaching."""
    disc_id = _find_numeric_id(params.faculty_name)
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
    """List scholars in *department* (basic info only)."""
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
    """Return *max_items* most-recent publications for the given scholar id."""
    pubs = _get_publications(params.scholar_id, params.max_items)
    return {"status": "ok", "publications": pubs}


# ---------------------------------------------------------------------------
# Internal fetch helpers
# ---------------------------------------------------------------------------

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
            out.append(
                {
                    "title": pub.get("title"),
                    "year": pub.get("publicationDate", {}).get("year"),
                    "journal": pub.get("journal"),
                    "doi": pub.get("doi"),
                }
            )
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
            out.append({"title": g.get("title"), "funder": g.get("funderName")})
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


__all__ = [
    "fetch_profile_by_name",
    "search_department",
    "list_publications",
]

# ---------------------------------------------------------------------------
# Compatibility wrapper: class Tools expected by some Open WebUI versions
# ---------------------------------------------------------------------------

class Tools:  # noqa: D101 – thin wrapper class for WebUI autodiscovery
    """Expose module-level functions through a class interface.

    Certain Open WebUI builds look for a `Tools` class when loading python
    modules. This minimal shim delegates to the standalone functions defined
    above, so you can use either style:

        from openwebui_uab_scholars import Tools  # class usage
        t = Tools()
        result = t.fetch_profile_by_name({"faculty_name": "Andrea Cherrington"})

    or directly call the free functions.
    """

    def fetch_profile_by_name(self, params):  # type: ignore[valid-type]
        if isinstance(params, dict):
            params = NameLookup(**params)
        return fetch_profile_by_name(params)

    def search_department(self, params):  # type: ignore[valid-type]
        if isinstance(params, dict):
            params = DepartmentSearch(**params)
        return search_department(params)

    def list_publications(self, params):  # type: ignore[valid-type]
        if isinstance(params, dict):
            params = PublicationsOnly(**params)
        return list_publications(params) 