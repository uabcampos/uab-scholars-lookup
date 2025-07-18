import json
import unicodedata
import time
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional, List
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- SQLite-based cache (from profile_cache.py) ---
CACHE_PATH = Path("/tmp/profile_cache.sqlite")
TTL_SECS = 60 * 60 * 24  # 24 hours

MAX_UID = 6000


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

def handler(request):
    try:
        body = request.get_json()
        department = body.get("department")
        related_terms = body.get("related_terms") or []
        role_keywords = body.get("role_keywords") or []
        max_results = body.get("max_results", 25)
        if not department:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Missing department"})
            }
        dept_terms = [department.lower()] + [t.lower() for t in related_terms]
        role_kw    = [k.lower() for k in role_keywords]
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
                if len(matches) >= max_results:
                    break
        return {
            "statusCode": 200,
            "body": json.dumps({"matches": matches, "count": len(matches)})
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        } 