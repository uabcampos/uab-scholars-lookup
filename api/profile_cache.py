"""SQLite-based cache for Scholars user profiles.

Keeps JSON blobs for 24 hours to avoid repeat network calls.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional, Dict, Any
import threading

CACHE_PATH = Path(__file__).resolve().parent / "profile_cache.sqlite"
TTL_SECS = 60 * 60 * 24  # 24 hours

def _get_conn() -> sqlite3.Connection:
    """Return a NEW SQLite connection with WAL enabled.

    Opening a fresh connection for each cache access completely sidesteps the
    cross-thread object-reuse error (ProgrammingError) that can occur when
    worker threads pick up a connection created in a different thread.  WAL
    mode keeps multiple read connections fast and safe while still allowing
    writes.
    """
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


def get(uid: str) -> Optional[Dict[str, Any]]:
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


def put(uid: str, js: Dict[str, Any]) -> None:
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO profile_cache(uid, json, ts) VALUES (?,?,?)",
        (uid, json.dumps(js), int(time.time())),
    )
    conn.commit()
    conn.close() 