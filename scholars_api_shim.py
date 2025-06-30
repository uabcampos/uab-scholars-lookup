"""scholars_api_shim

Drop-in compatibility layer for the June-2025 Scholars@UAB API update.
Importing this module once per process will monkey-patch requests so that
legacy code which still sends "type"/"objectType" keys continues to work.
It also auto-adds a default pagination block for /api/users searches when
missing.

Usage (add as the first import in any script that calls the Scholars API):

    import scholars_api_shim  # noqa: F401

Nothing else needs to change in legacy code.
"""
from __future__ import annotations
import copy
import types
from typing import Any, Dict
import requests

_ORIG_POST = requests.Session.post  # original bound method
_ORIG_REQ_POST = requests.post      # original function

DEFAULT_PAGINATION = {"startFrom": 0, "perPage": 25}


def _transform_payload(obj: Any) -> None:
    """Recursively mutate dict/list payloads in-place."""
    if isinstance(obj, dict):
        # Promote keys
        if "objectType" in obj and "category" not in obj:
            obj["category"] = obj.pop("objectType")
        if "type" in obj and "category" not in obj:
            obj["category"] = obj.pop("type")
        if "object" in obj and "category" not in obj:
            obj["category"] = obj.pop("object")

        # Inject default pagination for /api/users query payloads
        if "params" in obj and isinstance(obj["params"], dict):
            if obj.get("pagination") is None and obj["params"].get("by") == "text" and obj["params"].get("category") == "user":
                obj["pagination"] = copy.deepcopy(DEFAULT_PAGINATION)

        for v in obj.values():
            _transform_payload(v)

    elif isinstance(obj, list):
        for item in obj:
            _transform_payload(item)


def _patched_post(self_or_url, url: str | None = None, *args, **kw):
    """Wrapper around requests.post / Session.post"""
    # Distinguish between method vs function call style
    is_session_call = isinstance(self_or_url, requests.Session)
    sess = self_or_url if is_session_call else None
    dest_url = url if is_session_call else self_or_url

    if "json" in kw and isinstance(kw["json"], (dict, list)):
        js_copy = copy.deepcopy(kw["json"])
        _transform_payload(js_copy)
        kw["json"] = js_copy

    if is_session_call:
        return _ORIG_POST(sess, dest_url, *args, **kw)
    return _ORIG_REQ_POST(dest_url, *args, **kw)


# Apply monkey-patches only once
if not getattr(requests, "_scholars_api_patched", False):
    requests.Session.post = _patched_post  # type: ignore[assignment]
    requests.post = _patched_post  # type: ignore[assignment]
    requests._scholars_api_patched = True 