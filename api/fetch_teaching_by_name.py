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
API_TEACHING = f"{BASE_URL}/api/teachingActivities/linkedTo"
SEARCH_PAGE_SIZE = 500
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
            time.sleep(0.1)
        except Exception:
            break

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

# --- Vercel handler ---
def handler(request):
    try:
        body = request.get_json()
        faculty_name = body.get("faculty_name")
        since_year = body.get("since_year")
        until_year = body.get("until_year")
        limit = body.get("limit")
        keyword = body.get("keyword")
        level = body.get("level")
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
                year = int(flat.get("startYear") or 0)
                if since_year and year < since_year:
                    continue
                if until_year and year > until_year:
                    continue
                if keyword and keyword.lower() not in flat.get("title", "").lower():
                    continue
                if level and level.lower() not in (flat.get("type", "").lower()):
                    continue
                acts.append(flat); cnt += 1
                if limit and cnt >= limit:
                    break
            if limit and cnt >= limit:
                break
        return {
            "statusCode": 200,
            "body": json.dumps({"teaching": acts})
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        } 