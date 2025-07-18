import json
import unicodedata
import time
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional
import requests

# --- SQLite-based cache (from profile_cache.py) ---
CACHE_PATH = Path("/tmp/profile_cache.sqlite")
TTL_SECS = 60 * 60 * 24  # 24 hours

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(CACHE_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS profile_cache (
                uid TEXT PRIMARY KEY,
                json TEXT NOT NULL,
                ts  INTEGER NOT NULL
            )"""
    )
    return conn

def cache_get(uid: str) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    cur = conn.execute(
        "SELECT json, ts FROM profile_cache WHERE uid=?", (uid,)
    ).fetchone()
    conn.close()
    if not cur:
        return None
    js, ts = cur
    if (time.time() - ts) > TTL_SECS:
        return None
    try:
        return json.loads(js)
    except Exception:
        return None

def cache_put(uid: str, js: Dict[str, Any]) -> None:
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO profile_cache(uid, json, ts) VALUES (?,?,?)",
        (uid, json.dumps(js), int(time.time())),
    )
    conn.commit()
    conn.close()

# --- Config ---
BASE_URL = "https://scholars.uab.edu"
API_USERS = f"{BASE_URL}/api/users"
HEADERS = {
    "Accept":       "application/json, text/html, */*",
    "Content-Type": "application/json",
    "User-Agent":   "UAB-Scholars-Tool/1.0",
}
session = requests.Session()

# --- Helpers ---
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

def get_name_variations(full_name: str):
    parts = full_name.split()
    first, last = parts[0], parts[-1]
    variations = [(first, last)]
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
        alt_name = name_map[full_name]
        alt_parts = alt_name.split()
        if len(alt_parts) > 1:
            variations.append((alt_parts[0], alt_parts[-1]))
            if len(alt_parts) > 2:
                variations.append((f"{alt_parts[0]} {alt_parts[1]}", alt_parts[-1]))
        else:
            variations.append((alt_name, last))
    if "-" in full_name:
        no_hyphen = full_name.replace("-", " ")
        no_hyphen_parts = no_hyphen.split()
        if len(no_hyphen_parts) > 1:
            variations.append((no_hyphen_parts[0], no_hyphen_parts[-1]))
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
                    return str(u.get("discoveryId") or u.get("objectId"))
        except Exception:
            continue
    return None

def fetch_user_js(identifier: str) -> Optional[Dict[str, Any]]:
    cached = cache_get(identifier)
    if cached is not None:
        return cached
    try:
        r = session.get(f"{API_USERS}/{identifier}", headers=HEADERS, timeout=15)
        r.raise_for_status()
        js = r.json()
        if isinstance(js, list):
            js = js[0] if js else None
        elif isinstance(js, dict) and "resource" in js:
            js = js["resource"][0] if js["resource"] else None
        if js:
            cache_put(identifier, js)
        return js
    except Exception:
        return None

def extract_ri(raw):
    if isinstance(raw, str):
        return clean_text(raw)
    return "; ".join(clean_text(x.get("value") or x.get("text") or "") for x in raw if isinstance(x, dict))

# --- Vercel handler ---
def handler(request):
    try:
        body = request.get_json()
        faculty_name = body.get("faculty_name")
        if not faculty_name:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Missing faculty_name"})
            }
        disc_id = find_disc_id(faculty_name)
        if not disc_id:
            return {
                "statusCode": 404,
                "body": json.dumps({"error": "Faculty not found"})
            }
        js = fetch_user_js(disc_id)
        if not js:
            return {
                "statusCode": 404,
                "body": json.dumps({"error": "Error fetching user data"})
            }
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
        return {
            "statusCode": 200,
            "body": json.dumps({"profile": profile})
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        } 