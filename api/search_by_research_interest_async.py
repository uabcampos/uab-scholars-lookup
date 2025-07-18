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

def extract_research_text(js: Dict[str, Any]) -> str:
    parts: List[str] = []
    ri_raw = js.get("researchInterests", "")
    if isinstance(ri_raw, str):
        parts.append(ri_raw)
    elif isinstance(ri_raw, list):
        parts.extend(
            clean_text(item.get("value") or item.get("text") or "")
            for item in ri_raw if isinstance(item, dict)
        )
    for key, val in js.items():
        if not key.startswith("tabSummary"):
            continue
        if isinstance(val, str):
            parts.append(val)
        elif isinstance(val, dict):
            parts.append(clean_text(val.get("value") or val.get("text") or ""))
        elif isinstance(val, list):
            parts.extend(
                clean_text(item.get("value") or item.get("text") or "")
                for item in val if isinstance(item, dict)
            )
    return " ".join(parts).lower()

def handler(request):
    try:
        body = request.get_json()
        search_terms = body.get("search_terms")
        chunk_size = body.get("chunk_size", 500)
        min_id = body.get("min_id", 1)
        max_id = body.get("max_id", MAX_UID)
        max_results = body.get("max_results", 1000)
        if not search_terms or not isinstance(search_terms, list):
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Missing or invalid search_terms"})
            }
        terms = [t.lower() for t in search_terms]
        matches: List[Dict[str, Any]] = []
        uid = min_id
        while uid <= max_id and len(matches) < max_results:
            remaining_needed = max_results - len(matches)
            this_chunk = min(chunk_size, remaining_needed)
            chunk_end = min(uid + this_chunk - 1, max_id)
            with ThreadPoolExecutor(max_workers=10) as pool:
                fut_to_uid = {
                    pool.submit(fetch_user_js, str(i)): i
                    for i in range(uid, chunk_end + 1)
                }
                for fut in as_completed(fut_to_uid):
                    if len(matches) >= max_results:
                        for pending in fut_to_uid:
                            pending.cancel()
                        break
                    js = fut.result()
                    if not js:
                        continue
                    joined = extract_research_text(js)
                    if any(t in joined for t in terms):
                        matches.append({
                            "objectId": js["objectId"],
                            "discoveryUrlId": js["discoveryUrlId"],
                            "firstName": js["firstName"],
                            "lastName": js["lastName"],
                            "email": js.get("emailAddress", {}).get("address", ""),
                        })
            uid = chunk_end + 1
        return {
            "statusCode": 200,
            "body": json.dumps({"matches": matches[:max_results], "count": len(matches)})
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        } 