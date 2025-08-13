"""
OpenWebUI Tool: UAB Scholars (direct API)
author: Chris Campos and Ryan Melvin
date: 2024-06-13
version: 0.2.1
description: |
    OpenWebUI agentic tool - queries UAB Scholars data via the public UAB Scholars API backend.
    Handles lookup by name for profiles, publications, grants, or teaching info.
requirements: requests, pydantic
"""

from typing import Any, Awaitable, Callable
from pydantic import BaseModel, Field
import asyncio
import requests
import re

UAB_API_BASE = "https://scholars.uab.edu/api"

async def _noop_event_emitter(event: Any) -> None:
    pass

class Tools:
    def __init__(self):
        self.api_base = UAB_API_BASE.rstrip("/")

    async def profile_lookup_agent(
        self,
        query: str,
        __event_emitter__: Callable[[Any], Awaitable[None]] = _noop_event_emitter,
        **user,
    ) -> str:
        """
        Main entrypoint for UAB Scholars lookups, now powered by direct UAB Scholars API.
        Args:
            query (str): User's text (name or question)
        Returns:
            str: Full JSON output from UAB Scholars API.
        """
        async def emit(status, done=False):
            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": status, "done": done}}
                )
        try:
            await emit(f"Using direct UAB Scholars API for lookup. Input: {repr(query)}")
            name = self._extract_best_name(query)
            await emit(f"Recognized name for Scholar lookup: “{name}”")
            result = await asyncio.to_thread(self._fetch_scholar_snapshot, name, emit)
            await emit("Done!", done=True)
            return result
        except Exception as e:
            msg = f"Scholars Lookup Error: {e}"
            await emit(msg, done=True)
            return msg

    def _extract_best_name(self, text):
        # Use simple capitalized word pair for "Firstname Lastname"
        name_matches = re.findall(r"\b([A-Z][a-z]+ [A-Z][a-z]+)\b", text)
        if name_matches:
            return name_matches[0]
        return text.strip()

    def _fetch_scholar_snapshot(self, name, emit=None):
        url = f"{self.api_base}/fetch_scholar_by_name"
        payload = {"faculty_name": name}
        if emit:
            try:
                asyncio.run(emit(f"POST {url} with payload {payload}"))
            except RuntimeError:
                pass
        resp = requests.post(url, json=payload, timeout=20)
        if resp.status_code != 200:
            raise Exception(f"UAB Scholars API error: HTTP {resp.status_code}: {resp.text}")
        raw = resp.json()
        
        # The API now returns enhanced bio information including tabSummaryAbout
        # The bio field will contain comprehensive information from both overview and tabSummaryAbout
        import json
        return json.dumps(raw, ensure_ascii=False, indent=2)

    def _fetch_profile(self, name, emit=None):
        url = f"{self.api_base}/fetch_profile_by_name"
        payload = {"faculty_name": name}
        if emit:
            try:
                asyncio.run(emit(f"POST {url} ..."))
            except RuntimeError:
                pass
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _fetch_publications(self, name, limit=5, emit=None):
        url = f"{self.api_base}/fetch_publications_by_name"
        payload = {"faculty_name": name, "limit": limit}
        if emit:
            try:
                asyncio.run(emit(f"POST {url} ..."))
            except RuntimeError:
                pass
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _fetch_grants(self, name, limit=3, emit=None):
        url = f"{self.api_base}/fetch_grants_by_name"
        payload = {"faculty_name": name, "limit": limit}
        if emit:
            try:
                asyncio.run(emit(f"POST {url} ..."))
            except RuntimeError:
                pass
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _fetch_teaching(self, name, limit=3, emit=None):
        url = f"{self.api_base}/fetch_teaching_by_name"
        payload = {"faculty_name": name, "limit": limit}
        if emit:
            try:
                asyncio.run(emit(f"POST {url} ..."))
            except RuntimeError:
                pass
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json() 