"""
UAB Scholars Search Tool

A Python tool for searching and retrieving information about UAB faculty members,
including their profiles, publications, grants, and teaching activities.

Key Features:
- Search faculty by name
- Search faculty by department (using API)
- Search faculty by expertise/keywords
- Retrieve detailed profiles
- Get publications, grants, and teaching activities
- Count faculty in departments

Example Usage:
    from uab_scholars_tool import Tools
    import asyncio

    # Create tool instance
    tool = Tools()

    # Search for a faculty member
    async def search_faculty():
        result = await tool.search_scholars("Andrea Cherrington")
        print(result)

    # Count faculty in a department
    count = tool.count_faculty_in_department("Preventive Medicine")
    print(f"Faculty in Preventive Medicine: {count}")

    # Search for faculty by expertise
    async def search_expertise():
        keywords = [
            "behavioral intervention",
            "digital coaching",
            "mobile health",
            "e-health"
        ]
        result = await tool.search_by_expertise(
            keywords=keywords,
            start_id=1,
            end_id=500,
            max_results=3
        )
        print(result)

    # Run async examples
    asyncio.run(search_faculty())
    asyncio.run(search_expertise())

Version History:
---------------
v0.1.0 (2024-03-19)
- Initial release
- Basic functionality for searching scholars and retrieving profiles
- Support for publications, grants, and teaching activities
- Department-based search and faculty counting

v0.1.1 (2024-03-20)
- Added concurrent requests for faster department faculty counting
- Improved error handling in API requests
- Added timeout parameters to prevent hanging requests
- Enhanced name variation handling for better search results

v0.1.2 (2024-03-21)
- Fixed grants retrieval functionality
- Added proper error handling for API responses
- Improved response formatting for better model compatibility
- Added support for both numeric IDs and discovery URL IDs

v0.1.3 (2024-03-22)
- Added slugify function for URL-friendly text conversion
- Updated search_scholars method to use slugified name for profile URL

v0.1.4 (2024-03-23)
- Added expertise-based search functionality
- Implemented keyword matching across profiles, publications, and grants
- Added support for ranking scholars by expertise relevance
- Enhanced search results with detailed match information

Author: Chris Campos
Version: 0.1.4
License: MIT
"""

import requests
import json
import time
import unicodedata
import re
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Any, Optional, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
import concurrent.futures
import scholars_api_shim  # noqa: F401

class Tools:
    class Valves(BaseModel):
        """Configuration options for the UAB Scholars tool."""
        
        max_results: int = Field(
            default=10,
            description="Maximum number of scholars to retrieve",
        )
        include_publications: bool = Field(
            default=True,
            description="Whether to include publications in the results",
        )
        include_grants: bool = Field(
            default=True,
            description="Whether to include grants in the results",
        )
        include_teaching: bool = Field(
            default=True,
            description="Whether to include teaching activities in the results",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.base_url = "https://scholars.uab.edu/api"
        self.headers = {
            "Accept": "application/json, text/html, */*",
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
        }

    def clean_text(self, s: str) -> str:
        """Normalize unicode, replace mojibake and fancy punctuation, collapse whitespace."""
        if not isinstance(s, str):
            return ""
        t = unicodedata.normalize("NFKC", s)
        t = t.replace("‚Äì", "-")
        for orig, repl in [
            ("\u2013", "-"), ("\u2014", "-"),
            (""", '"'), (""", '"'),
            ("'", "'"), ("'", "'"),
        ]:
            t = t.replace(orig, repl)
        return " ".join(t.split())

    async def _emit_status(self, description: str, status: str = "in_progress", done: bool = False, __event_emitter__=None):
        """Helper method to emit status updates."""
        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "status": status,
                        "description": description,
                        "done": done,
                    },
                }
            )

    async def _emit_citation(self, name: str, bio: str, url: str, __event_emitter__=None):
        """Helper method to emit citations."""
        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "citation",
                    "data": {
                        "document": [
                            f"UAB Scholar: {name}",
                            bio,
                        ],
                        "metadata": [{"source": url}],
                        "source": {"name": f"UAB Scholars - {name}"},
                    },
                }
            )

    def get_name_variations(self, full_name: str) -> list:
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
            "Yu-Mei": "Yu Mei"
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
            variations.append((no_hyphen_parts[0], no_hyphen_parts[-1]))
            if len(no_hyphen_parts) > 2:
                variations.append((no_hyphen_parts[0], f"{no_hyphen_parts[-2]} {no_hyphen_parts[-1]}"))
        if "Jr" in last or "Sr" in last:
            base_last = last.replace("Jr", "").replace("Sr", "").strip()
            variations.append((first, base_last))
            variations.append((first, f"{base_last}, Jr."))
            variations.append((first, f"{base_last}, Sr."))
            if len(parts) > 2:
                variations.append((f"{first} {parts[1]}", base_last))
                variations.append((f"{first} {parts[1]}", f"{base_last}, Jr."))
                variations.append((f"{first} {parts[1]}", f"{base_last}, Sr."))
        if len(parts) > 2 and len(parts[-2]) == 1:
            variations.append((f"{first} {parts[-2]}", last))
        return variations

    def find_disc_id(self, full_name: str) -> tuple:
        """
        Find the discoveryUrlId for a scholar by robust name matching.
        Prefer exact matches, then partial matches. No fallback to PubMed.
        Returns a tuple of (discoveryUrlId, search_details) where search_details contains debugging information.
        """
        variations = self.get_name_variations(full_name)
        best_match = None
        best_profile_score = -1
        search_details = {
            "original_query": full_name,
            "tried_variations": [],
            "api_responses": []
        }
        
        for first, last in variations:
            search_query = f"{first} {last}"
            search_details["tried_variations"].append(search_query)
            
            payload = {"params": {"by": "text", "type": "user", "text": search_query}}
            try:
                r = requests.post(f"{self.base_url}/users", json=payload, headers=self.headers, timeout=15)
                r.raise_for_status()
                response_data = r.json()
                
                # Record API response for debugging
                api_response = {
                    "query": search_query,
                    "status_code": r.status_code,
                    "total_results": response_data.get("pagination", {}).get("total", 0),
                    "matches": []
                }
                
                for u in response_data.get("resource", []):
                    match_info = {
                        "firstName": u.get("firstName", ""),
                        "lastName": u.get("lastName", ""),
                        "discoveryUrlId": u.get("discoveryUrlId", ""),
                        "hasPositions": bool(u.get("positions")),
                        "hasPublications": bool(u.get("publications"))
                    }
                    api_response["matches"].append(match_info)
                    
                    # Exact match
                    if (u.get("firstName", "").lower() == first.lower() and
                        u.get("lastName", "").lower() == last.lower()):
                        search_details["api_responses"].append(api_response)
                        return u.get("discoveryUrlId"), search_details
                    
                    # Partial match (e.g., first initial, middle name, etc.)
                    if (u.get("lastName", "").lower() == last.lower() and
                        (u.get("firstName", "").lower().startswith(first.lower()) or
                         first.lower().startswith(u.get("firstName", "").lower()))):
                        # Score profile completeness (positions + publications)
                        score = 0
                        if u.get("positions"): score += 1
                        if u.get("publications"): score += 1
                        if score > best_profile_score:
                            best_profile_score = score
                            best_match = u.get("discoveryUrlId")
                
                search_details["api_responses"].append(api_response)
                
            except Exception as e:
                search_details["api_responses"].append({
                    "query": search_query,
                    "error": str(e)
                })
                continue
                
        return best_match, search_details

    def slugify(self, text: str) -> str:
        """Convert text to URL-friendly slug."""
        # Convert to lowercase and normalize unicode
        text = unicodedata.normalize('NFKD', text.lower())
        # Remove special characters and replace spaces with hyphens
        text = re.sub(r'[^a-z0-9\s-]', '', text)
        # Replace spaces with hyphens
        text = re.sub(r'\s+', '-', text)
        # Remove multiple hyphens
        text = re.sub(r'-+', '-', text)
        # Remove leading/trailing hyphens
        return text.strip('-')

    async def search_scholars(
        self, query: str, department: str = "", __event_emitter__=None
    ) -> str:
        """
        Search UAB Scholars for people matching the query.
        Always prefer UAB Scholars data. No fallback to PubMed.
        :param query: The search query for names or research topics.
        :param department: Optional specific department to search within.
        :return: JSON string containing scholar profiles.
        """
        await self._emit_status(f"Initiating search for UAB scholars: {query}", __event_emitter__=__event_emitter__)

        results = []
        disc_id, search_details = self.find_disc_id(query)
        if not disc_id:
            await self._emit_status(
                "No scholars found matching the search criteria",
                status="complete",
                done=True,
                __event_emitter__=__event_emitter__
            )
            return json.dumps({
                "type": "scholar_search_results",
                "status": "not_found",
                "message": f"No UAB Scholars profile found for '{query}'. Please check the spelling or try a different name.",
                "debug_info": {
                    "search_details": search_details,
                    "suggestion": "Try using the full name with middle initial if available, or check for alternative spellings."
                },
                "results": []
            })
            
        try:
            profile_url = f"{self.base_url}/users/{disc_id}"
            response = requests.get(profile_url, headers=self.headers, timeout=15)
            response.raise_for_status()
            profile_data = response.json()
            
            if department:
                positions = profile_data.get("positions", [])
                dept_match = any(
                    department.lower() in (p.get("department","") or "").lower()
                    for p in positions
                )
                if not dept_match:
                    await self._emit_status(
                        "No scholars found in specified department",
                        status="complete",
                        done=True,
                        __event_emitter__=__event_emitter__
                    )
                    return json.dumps({
                        "type": "scholar_search_results",
                        "status": "not_found",
                        "message": f"No UAB Scholars profile found for '{query}' in department '{department}'.",
                        "debug_info": {
                            "search_details": search_details,
                            "found_profile": {
                                "name": f"{profile_data.get('firstName', '')} {profile_data.get('lastName', '')}",
                                "departments": [p.get("department", "") for p in positions if p.get("department")],
                                "url": f"https://scholars.uab.edu/{disc_id}"
                            },
                            "suggestion": "The scholar was found but is not in the specified department. Try searching without a department filter."
                        },
                        "results": []
                    })
            
            publications = []
            if self.valves.include_publications:
                publications = await self._get_publications(disc_id, __event_emitter__)
            grants = []
            if self.valves.include_grants:
                grants = await self._get_grants(disc_id, __event_emitter__)
            teaching = []
            if self.valves.include_teaching:
                teaching = await self._get_teaching_activities(disc_id, __event_emitter__)
            
            name = f"{profile_data.get('firstName', '')} {profile_data.get('lastName', '')}".strip()
            positions = profile_data.get("positions", [])
            department = next((p.get("department", "") for p in positions if p.get("department")), "N/A")
            position = next((p.get("position", "") for p in positions if p.get("position")), "N/A")
            
            # Get teaching interests from profile
            teaching_interests = profile_data.get("teachingSummary", "")
            
            formatted_pubs = []
            for pub in publications[:3]:
                pub_data = {
                    "title": pub.get("title", "N/A"),
                    "journal": pub.get("journal", "N/A"),
                    "year": pub.get("year", "N/A"),
                    "authors": pub.get("authors", "N/A"),
                }
                if pub.get("url"):
                    pub_data["url"] = pub["url"]
                formatted_pubs.append(pub_data)
            
            profile_url = f"https://scholars.uab.edu/{profile_data.get('discoveryUrlId', disc_id)}"
            scholar_data = {
                "type": "scholar_search_results",
                "status": "found",
                "message": f"Found scholar: {name}",
                "profile": {
                    "name": name,
                    "department": department,
                    "position": position,
                    "url": profile_url,
                    "teaching_interests": teaching_interests
                },
                "publications": {
                    "total": len(publications),
                    "recent": formatted_pubs
                },
                "grants": {
                    "total": len(grants),
                    "list": grants
                },
                "teaching_activities": {
                    "total": len(teaching),
                    "list": teaching
                }
            }
            results.append(scholar_data)
            await self._emit_citation(
                name=name,
                bio=profile_data.get("bio", ""),
                url=profile_url,
                __event_emitter__=__event_emitter__
            )
        except Exception as e:
            await self._emit_status(
                f"Error processing scholar: {str(e)}",
                status="warning",
                __event_emitter__=__event_emitter__
            )
            return json.dumps({
                "type": "scholar_search_results",
                "status": "error",
                "message": f"Error processing scholar: {str(e)}",
                "debug_info": {
                    "search_details": search_details,
                    "error_details": str(e)
                },
                "results": []
            })
        
        await self._emit_status(
            f"Found {len(results)} matching scholars",
            status="complete",
            done=True,
            __event_emitter__=__event_emitter__
        )
        return json.dumps({
            "type": "scholar_search_results",
            "status": "success",
            "message": f"Found {len(results)} matching scholars",
            "results": results
        }, ensure_ascii=False, indent=2)

    async def get_scholar_by_id(
        self, scholar_id: str, __event_emitter__=None
    ) -> str:
        """
        Retrieve a specific scholar's profile by ID.
        """
        await self._emit_status(f"Retrieving UAB scholar with ID: {scholar_id}", __event_emitter__=__event_emitter__)
        
        try:
            # Determine if input is numeric ID or discovery URL ID
            if scholar_id.isdigit():
                numeric_id = int(scholar_id)
                profile_data = await self._get_scholar_profile(numeric_id, __event_emitter__)
                disc_url_id = profile_data.get("discoveryUrlId", scholar_id)
            else:
                disc_url_id = scholar_id
                # Get the numeric ID from the discovery URL ID
                search_url = f"{self.base_url}/users"
                search_payload = {
                    "params": {
                        "by": "text",
                        "type": "user",
                        "text": disc_url_id
                    }
                }
                response = requests.post(search_url, json=search_payload, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                scholars = data.get("items", [])
                
                if not scholars:
                    raise ValueError(f"No scholar found with ID: {scholar_id}")
                
                numeric_id = scholars[0].get("objectId")
                profile_data = await self._get_scholar_profile(numeric_id, __event_emitter__)
            # Get publications if requested
            publications = []
            if self.valves.include_publications:
                publications = await self._get_publications(disc_url_id, __event_emitter__)
            # Get grants if requested
            grants = []
            if self.valves.include_grants:
                grants = await self._get_grants(disc_url_id, __event_emitter__)
            # Get teaching activities if requested
            teaching = []
            if self.valves.include_teaching:
                teaching = await self._get_teaching_activities(disc_url_id, __event_emitter__)
            # Combine all data
            scholar_data = {
                "type": "scholar_profile",
                "status": "success",
                "message": f"Retrieved profile for {profile_data.get('firstName', '')} {profile_data.get('lastName', '')}",
                "profile": profile_data,
                "publications": publications,
                "grants": grants,
                "teaching_activities": teaching,
                "url": f"https://scholars.uab.edu/{disc_url_id}"
            }
            # Emit citation
            name = f"{profile_data.get('firstName', '')} {profile_data.get('lastName', '')}"
            await self._emit_citation(
                name=name,
                bio=profile_data.get("bio", ""),
                url=scholar_data["url"],
                __event_emitter__=__event_emitter__
            )
            await self._emit_status(
                f"Retrieved detailed information for {profile_data.get('firstName', '')} {profile_data.get('lastName', '')}",
                status="complete",
                done=True,
                __event_emitter__=__event_emitter__
            )
            return json.dumps(scholar_data, ensure_ascii=False, indent=2)
        except (requests.exceptions.RequestException, ValueError) as e:
            await self._emit_status(
                f"Error retrieving scholar: {str(e)}",
                status="error",
                done=True,
                __event_emitter__=__event_emitter__
            )
            return json.dumps({
                "type": "scholar_profile",
                "status": "error",
                "message": str(e),
                "results": []
            })

    async def search_by_department(
        self, department: str, __event_emitter__=None
    ) -> str:
        """
        Search for all scholars in a specific department using the API.
        
        :param department: The department name or substring to search for.
        :return: JSON string containing scholar profiles (list of dicts), or a list with a single dict with an 'error' key.
        """
        await self._emit_status(f"Searching for scholars in department: {department}", __event_emitter__=__event_emitter__)
        
        search_url = f"{self.base_url}/users"
        results = []
        start = 0
        per_page = 100
        
        while True:
            search_payload = {
                "params": {
                    "by": "text",
                    "type": "user",
                    "text": department
                },
                "pagination": {
                    "perPage": per_page,
                    "startFrom": start
                }
            }
            try:
                response = requests.post(search_url, json=search_payload, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                total = data.get("pagination", {}).get("total", 0)
                await self._emit_status(
                    f"Retrieved {len(results)} of {total} potential matches",
                    __event_emitter__=__event_emitter__
                )
                for scholar in data.get("resource", []):
                    positions = scholar.get("positions", [])
                    if any(department.lower() in (p.get("department","") or "").lower() for p in positions):
                        disc_id = scholar.get("discoveryUrlId")
                        if disc_id:
                            profile_data = await self._get_scholar_profile(scholar.get("objectId"), __event_emitter__)
                            # Ensure profile_data is a dict
                            if not isinstance(profile_data, dict):
                                # Optionally log or collect the error here
                                continue
                            publications = []
                            if self.valves.include_publications:
                                publications = await self._get_publications(disc_id, __event_emitter__)
                            grants = []
                            if self.valves.include_grants:
                                grants = await self._get_grants(disc_id, __event_emitter__)
                            teaching = []
                            if self.valves.include_teaching:
                                teaching = await self._get_teaching_activities(disc_id, __event_emitter__)
                            name = f"{profile_data.get('firstName', '')} {profile_data.get('lastName', '')}"
                            positions = profile_data.get("positions", [])
                            dept = next((p.get("department", "") for p in positions if p.get("department")), "N/A")
                            pos = next((p.get("position", "") for p in positions if p.get("position")), "N/A")
                            scholar_data = {
                                "type": "department_search_results",
                                "status": "found",
                                "message": f"Found scholar: {name}",
                                "profile": {
                                    "name": name,
                                    "department": dept,
                                    "position": pos,
                                    "url": f"https://scholars.uab.edu/{disc_id}"
                                },
                                "publications": {
                                    "total": len(publications),
                                    "recent": publications[:3]
                                },
                                "grants": {
                                    "total": len(grants),
                                    "list": grants
                                },
                                "teaching_activities": {
                                    "total": len(teaching),
                                    "list": teaching
                                }
                            }
                            results.append(scholar_data)
                if start + per_page >= total:
                    break
                start += per_page
                time.sleep(0.1)
            except requests.exceptions.RequestException as e:
                error_message = f"API request error: {str(e)}"
                await self._emit_status(
                    error_message,
                    status="error",
                    done=True,
                    __event_emitter__=__event_emitter__
                )
                return json.dumps({
                    "type": "department_search_results",
                    "status": "error",
                    "message": error_message,
                    "results": []
                })
            except Exception as e:
                error_message = f"Error searching department: {str(e)}"
                await self._emit_status(
                    error_message,
                    status="error",
                    done=True,
                    __event_emitter__=__event_emitter__
                )
                return json.dumps({
                    "type": "department_search_results",
                    "status": "error",
                    "message": error_message,
                    "results": []
                })
        await self._emit_status(
            f"Found {len(results)} scholars in {department}",
            status="complete",
            done=True,
            __event_emitter__=__event_emitter__
        )
        return json.dumps({
            "type": "department_search_results",
            "status": "success",
            "message": f"Found {len(results)} scholars in {department}",
            "results": results
        }, ensure_ascii=False, indent=2)

    async def _get_scholar_profile(self, scholar_id: int, __event_emitter__=None) -> Dict:
        """Get and process a scholar's full profile."""
        await self._emit_status(f"Retrieving profile for scholar ID: {scholar_id}", __event_emitter__=__event_emitter__)
        
        profile_url = f"{self.base_url}/users/{scholar_id}"
        response = requests.get(profile_url, headers=self.headers)
        response.raise_for_status()
        js = response.json()
        
        # Extract profile information
        email = js.get("emailAddress", {}).get("address", "")
        orcid = js.get("orcid", "") or ""

        # departments and positions
        depts = [p.get("department","") for p in js.get("positions",[]) if p.get("department")]
        titles = [p.get("position","") for p in js.get("positions",[]) if p.get("position")]
        for appt in js.get("institutionalAppointments", []):
            if appt.get("position"):
                titles.append(appt["position"])

        # clean bio and teaching summary
        bio_clean = self.clean_text(js.get("overview", "").replace("\n", " "))
        teach_clean = self.clean_text(js.get("teachingSummary", "").replace("\n", " "))

        # research interests
        raw_ri = js.get("researchInterests", "")
        research = []
        if isinstance(raw_ri, str) and raw_ri.strip():
            research.append(self.clean_text(raw_ri))
        elif isinstance(raw_ri, list):
            for item in raw_ri:
                if isinstance(item, str):
                    research.append(self.clean_text(item))
                elif isinstance(item, dict):
                    v = item.get("value") or item.get("text") or item.get("description") or ""
                    research.append(self.clean_text(v))

        return {
            "objectId": js.get("objectId", ""),
            "discoveryUrlId": js.get("discoveryUrlId", ""),
            "firstName": js.get("firstName", ""),
            "lastName": js.get("lastName", ""),
            "email": email,
            "orcid": orcid,
            "department": "; ".join(sorted(set(depts))),
            "positions": "; ".join(sorted(set(titles))),
            "bio": bio_clean,
            "researchInterests": "; ".join(research),
            "teachingSummary": teach_clean,
            "hasThumbnail": js.get("hasThumbnail", False),
            "thumbnailUrl": f"https://scholars.uab.edu/thumbnails/{js.get('discoveryUrlId')}" if js.get("hasThumbnail") else None
        }

    async def _get_publications(self, disc_url_id: str, __event_emitter__=None) -> List[Dict]:
        await self._emit_status(f"Retrieving publications for {disc_url_id}", __event_emitter__=__event_emitter__)
        
        pubs_url = f"{self.base_url}/publications/linkedTo"
        publications = []
        start = 0
        per_page = 25
        
        while True:
            payload = {
                "objectId": disc_url_id,
                "objectType": "user",
                "pagination": {"perPage": per_page, "startFrom": start},
                "favouritesFirst": True,
                "sort": "dateDesc"
            }
            
            response = requests.post(pubs_url, json=payload, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            
            results = data.get("resource", [])
            if not results:
                break
                
            for pub in results:
                authors = "; ".join(a.get("fullName","") for a in pub.get("authors",[]))
                labels = "; ".join(lbl.get("value","") for lbl in pub.get("labels",[]))
                pd = pub.get("publicationDate", {})
                
                # Get the publication URL from the API response
                pub_url = None
                if pub.get("url"):
                    pub_url = pub["url"]
                elif pub.get("doi"):
                    pub_url = f"https://doi.org/{pub['doi']}"
                
                publications.append({
                    "publicationObjectId": pub.get("objectId",""),
                    "title": self.clean_text(pub.get("title","")),
                    "journal": pub.get("journal",""),
                    "doi": pub.get("doi",""),
                    "url": pub_url,  # Use the URL from API or constructed DOI URL
                    "year": pd.get("year",""),
                    "month": pd.get("month",""),
                    "day": pd.get("day",""),
                    "volume": pub.get("volume",""),
                    "issue": pub.get("issue",""),
                    "pages": pub.get("pagination",""),
                    "issn": pub.get("issn",""),
                    "labels": labels,
                    "authors": authors,
                })
                
            total = data.get("pagination",{}).get("total", 0)
            start += per_page
            if start >= total:
                break
                
            time.sleep(0.1)  # Small pause between requests
            
        await self._emit_status(f"Retrieved {len(publications)} publications", __event_emitter__=__event_emitter__)
        return publications

    async def _get_grants(self, disc_url_id: str, __event_emitter__=None) -> List[Dict]:
        """Get a scholar's grants."""
        await self._emit_status(f"Retrieving grants for {disc_url_id}", __event_emitter__=__event_emitter__)
        
        grants_url = f"{self.base_url}/grants/linkedTo"
        grants = []
        start = 0
        per_page = 25
        
        while True:
            payload = {
                "objectId": disc_url_id,
                "objectType": "user",
                "pagination": {"perPage": per_page, "startFrom": start},
                "favouritesFirst": True,
                "sort": "dateDesc"
            }
            
            try:
                response = requests.post(grants_url, json=payload, headers=self.headers, timeout=15)
                response.raise_for_status()
                data = response.json()
                
                # Try both "items" and "resource" keys as the API might use either
                results = data.get("items", []) or data.get("resource", [])
                if not results:
                    break
                    
                for grant in results:
                    d = grant.get("date1", {})
                    labels = "; ".join(lbl.get("value","") for lbl in grant.get("labels",[]))
                    
                    grants.append({
                        "grantObjectId": grant.get("objectId",""),
                        "title": self.clean_text(grant.get("title","")),
                        "funder": grant.get("funderName",""),
                        "awardType": grant.get("objectTypeDisplayName",""),
                        "year": d.get("year",""),
                        "month": d.get("month",""),
                        "day": d.get("day",""),
                        "labels": labels,
                    })
                    
                total = data.get("pagination",{}).get("total", 0)
                start += per_page
                if start >= total:
                    break
                    
                time.sleep(0.1)  # Small pause between requests
                
            except requests.exceptions.RequestException as e:
                await self._emit_status(
                    f"Error retrieving grants: {str(e)}",
                    status="warning",
                    __event_emitter__=__event_emitter__
                )
                break
            
        await self._emit_status(f"Retrieved {len(grants)} grants", __event_emitter__=__event_emitter__)
        return grants

    async def _get_teaching_activities(self, disc_url_id: str, __event_emitter__=None) -> List[Dict]:
        """
        Get teaching activities for a scholar.
        """
        await self._emit_status(f"Retrieving teaching activities for {disc_url_id}", __event_emitter__=__event_emitter__)
        
        teaching_url = f"{self.base_url}/teachingActivities/linkedTo"
        activities = []
        start = 0
        per_page = 50
        
        while True:
            payload = {
                "objectId": disc_url_id,
                "objectType": "user",
                "pagination": {"perPage": per_page, "startFrom": start}
            }
            
            try:
                response = requests.post(teaching_url, json=payload, headers=self.headers, timeout=15)
                response.raise_for_status()
                data = response.json()
                
                results = data.get("resource", [])
                if not results:
                    break
                    
                for act in results:
                    d1 = act.get("date1", {})
                    d2 = act.get("date2", {})
                    activities.append({
                        "teachingActivityObjectId": act.get("objectId", ""),
                        "type": act.get("objectTypeDisplayName", ""),
                        "title": self.clean_text(act.get("title", "")),
                        "startYear": d1.get("year", ""),
                        "startMonth": d1.get("month", ""),
                        "startDay": d1.get("day", ""),
                        "endYear": d2.get("year", ""),
                        "endMonth": d2.get("month", ""),
                        "endDay": d2.get("day", "")
                    })
                    
                total = data.get("pagination", {}).get("total", 0)
                start += per_page
                if start >= total:
                    break
                    
                time.sleep(0.1)  # Small pause between requests
                
            except Exception as e:
                await self._emit_status(
                    f"Error retrieving teaching activities: {str(e)}",
                    status="warning",
                    __event_emitter__=__event_emitter__
                )
                break
                
        await self._emit_status(f"Retrieved {len(activities)} teaching activities", __event_emitter__=__event_emitter__)
        return activities

    def count_faculty_in_department(self, department: str, return_list: bool = False) -> Union[int, List[Dict]]:
        """
        Count the number of unique faculty in the specified department.
        Optionally return a list of faculty members with their details.
        Uses concurrent requests to speed up the process.
        
        :param department: The department name to search for
        :param return_list: If True, returns a list of faculty members instead of just the count
        :return: Either the count (int) or a list of faculty members (List[Dict])
        """
        seen_ids = set()
        faculty_list = []
        max_id = 6000  # Upper bound on numeric user IDs
        workers = 20   # Number of concurrent threads
        
        def fetch_and_filter(uid: int) -> Optional[Dict]:
            """Fetch and filter a single user profile."""
            try:
                profile_url = f"{self.base_url}/users/{uid}"
                response = requests.get(profile_url, headers=self.headers, timeout=15)
                if response.status_code != 200:
                    return None
                    
                profile_data = response.json()
                
                # Check if any position matches the department
                positions = profile_data.get("positions", [])
                matches = [
                    p for p in positions
                    if department.lower() in (p.get("department","") or "").lower()
                ]
                
                if not matches:
                    return None
                    
                # Get discovery URL ID
                disc_id = profile_data.get("discoveryUrlId")
                if not disc_id:
                    return None
                    
                # Collect unique department names and position titles
                depts = sorted({p["department"].strip() for p in matches if p.get("department")})
                titles = sorted({p["position"].strip() for p in positions if p.get("position")})
                
                return {
                    "disc_id": disc_id,
                    "name": f"{profile_data.get('firstName', '')} {profile_data.get('lastName', '')}",
                    "email": profile_data.get("emailAddress", {}).get("address", ""),
                    "department": "; ".join(depts),
                    "position": "; ".join(titles),
                    "url": f"https://scholars.uab.edu/{disc_id}"
                }
                
            except Exception as e:
                print(f"Error processing ID {uid}: {str(e)}")
                return None
        
        # Use ThreadPoolExecutor for concurrent requests
        with ThreadPoolExecutor(max_workers=workers) as executor:
            # Submit all tasks
            future_to_id = {
                executor.submit(fetch_and_filter, uid): uid 
                for uid in range(1, max_id + 1)
            }
            
            # Process results as they complete
            for future in as_completed(future_to_id):
                result = future.result()
                if result:
                    disc_id = result.pop("disc_id")
                    if disc_id not in seen_ids:
                        seen_ids.add(disc_id)
                        if return_list:
                            faculty_list.append(result)
        
        if return_list:
            return faculty_list
        return len(seen_ids)

    async def get_faculty_list(self, department: str, __event_emitter__=None) -> str:
        """
        Get a list of all faculty members in a department.
        
        :param department: The department name to search for
        :return: JSON string containing list of faculty members
        """
        await self._emit_status(f"Retrieving faculty list for department: {department}", __event_emitter__=__event_emitter__)
        
        try:
            faculty_list = self.count_faculty_in_department(department, return_list=True)
            
            if not faculty_list:
                await self._emit_status(
                    "No faculty found in specified department",
                    status="complete",
                    done=True,
                    __event_emitter__=__event_emitter__
                )
                return json.dumps({
                    "type": "faculty_list",
                    "status": "not_found",
                    "message": f"No faculty found in department: {department}",
                    "results": []
                })
            
            await self._emit_status(
                f"Found {len(faculty_list)} faculty members in {department}",
                status="complete",
                done=True,
                __event_emitter__=__event_emitter__
            )
            
            return json.dumps({
                "type": "faculty_list",
                "status": "success",
                "message": f"Found {len(faculty_list)} faculty members in {department}",
                "results": faculty_list
            }, ensure_ascii=False, indent=2)
            
        except Exception as e:
            await self._emit_status(
                f"Error retrieving faculty list: {str(e)}",
                status="error",
                done=True,
                __event_emitter__=__event_emitter__
            )
            return json.dumps({
                "type": "faculty_list",
                "status": "error",
                "message": str(e),
                "results": []
            })

    async def scan_all_scholars_by_id(self, start_id=1, end_id=100, __event_emitter__=None):
        """
        Scan a range of numeric user IDs, fetch each profile, and aggregate expertise.
        Returns a list of scholar dicts (profile, publications, grants, teaching).
        """
        await self._emit_status(f"Scanning user IDs {start_id} to {end_id}...", __event_emitter__=__event_emitter__)
        scholars = []
        ids = list(range(start_id, end_id + 1))
        max_workers = 10

        def fetch_one(uid):
            try:
                profile_url = f"{self.base_url}/users/{uid}"
                response = requests.get(profile_url, headers=self.headers, timeout=10)
                if response.status_code != 200:
                    return None
                profile_data = response.json()
                disc_id = profile_data.get("discoveryUrlId")
                if not disc_id:
                    return None
                # Fetch publications, grants, teaching
                publications = []
                if self.valves.include_publications:
                    publications = self._get_publications_sync(disc_id)
                grants = []
                if self.valves.include_grants:
                    grants = self._get_grants_sync(disc_id)
                teaching = []
                if self.valves.include_teaching:
                    teaching = self._get_teaching_activities_sync(disc_id)
                # Build profile
                name = f"{profile_data.get('firstName', '')} {profile_data.get('lastName', '')}".strip()
                positions = profile_data.get("positions", [])
                department = next((p.get("department", "") for p in positions if p.get("department")), "N/A")
                position = next((p.get("position", "") for p in positions if p.get("position")), "N/A")
                teaching_interests = profile_data.get("teachingSummary", "")
                scholar = {
                    "profile": {
                        "name": name,
                        "department": department,
                        "position": position,
                        "url": f"https://scholars.uab.edu/{disc_id}",
                        "teaching_interests": teaching_interests
                    },
                    "publications": {"recent": publications[:3]},
                    "grants": {"list": grants},
                    "teaching_activities": {"list": teaching}
                }
                return scholar
            except Exception:
                return None

        # Synchronous helpers for concurrent.futures
        def _get_publications_sync(disc_id):
            try:
                pubs_url = f"{self.base_url}/publications/linkedTo"
                payload = {
                    "objectId": disc_id,
                    "objectType": "user",
                    "pagination": {"perPage": 10, "startFrom": 0},
                    "favouritesFirst": True,
                    "sort": "dateDesc"
                }
                r = requests.post(pubs_url, json=payload, headers=self.headers, timeout=10)
                r.raise_for_status()
                data = r.json()
                return data.get("resource", [])
            except Exception:
                return []
        def _get_grants_sync(disc_id):
            try:
                grants_url = f"{self.base_url}/grants/linkedTo"
                payload = {
                    "objectId": disc_id,
                    "objectType": "user",
                    "pagination": {"perPage": 10, "startFrom": 0}
                }
                r = requests.post(grants_url, json=payload, headers=self.headers, timeout=10)
                r.raise_for_status()
                data = r.json()
                return data.get("resource", [])
            except Exception:
                return []
        def _get_teaching_activities_sync(disc_id):
            try:
                teach_url = f"{self.base_url}/teachingActivities/linkedTo"
                payload = {
                    "objectId": disc_id,
                    "objectType": "user",
                    "pagination": {"perPage": 10, "startFrom": 0}
                }
                r = requests.post(teach_url, json=payload, headers=self.headers, timeout=10)
                r.raise_for_status()
                data = r.json()
                return data.get("resource", [])
            except Exception:
                return []
        # Attach helpers to self for use in fetch_one
        self._get_publications_sync = _get_publications_sync
        self._get_grants_sync = _get_grants_sync
        self._get_teaching_activities_sync = _get_teaching_activities_sync

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_uid = {executor.submit(fetch_one, uid): uid for uid in ids}
            for future in concurrent.futures.as_completed(future_to_uid):
                scholar = future.result()
                if scholar:
                    scholars.append(scholar)
        await self._emit_status(f"Finished scanning {len(scholars)} scholars.", __event_emitter__=__event_emitter__)
        return scholars

    async def search_by_expertise(
        self,
        keywords: List[str],
        start_id: int = 1,
        end_id: int = 500,
        max_results: int = 3,
        __event_emitter__=None
    ) -> str:
        """
        Search for scholars with expertise matching the provided keywords.
        
        Args:
            keywords: List of keywords to search for in scholar profiles
            start_id: Starting scholar ID to search from
            end_id: Ending scholar ID to search up to
            max_results: Maximum number of top matches to return
            __event_emitter__: Optional event emitter for status updates
            
        Returns:
            str: JSON string containing the search results
        """
        try:
            await self._emit_status(
                f"Searching for expertise in: {', '.join(keywords)}",
                __event_emitter__=__event_emitter__
            )
            
            # Step 1: Scan scholars by ID
            all_scholars = await self.scan_all_scholars_by_id(
                start_id=start_id,
                end_id=end_id,
                __event_emitter__=__event_emitter__
            )
            
            if not all_scholars:
                return json.dumps({
                    "type": "expertise_search_results",
                    "status": "error",
                    "message": "No scholars found in the specified range",
                    "results": []
                })
            
            await self._emit_status(
                f"Found {len(all_scholars)} scholars to analyze",
                __event_emitter__=__event_emitter__
            )
            
            # Step 2: Aggregate expertise and filter by topic
            matches = []
            for scholar in all_scholars:
                try:
                    profile = scholar.get("profile", {})
                    expertise_text = " ".join([
                        profile.get("teaching_interests", ""),
                        profile.get("department", ""),
                        profile.get("position", ""),
                        # Publications
                        " ".join(pub.get("title", "") for pub in scholar.get("publications", {}).get("recent", [])),
                        # Grants
                        " ".join(grant.get("title", "") for grant in scholar.get("grants", {}).get("list", [])),
                    ]).lower()
                    
                    # Count keyword matches
                    match_count = sum(kw.lower() in expertise_text for kw in keywords)
                    if match_count > 0:
                        matches.append((match_count, scholar))
                except Exception as e:
                    await self._emit_status(
                        f"Error processing scholar: {str(e)}",
                        status="warning",
                        __event_emitter__=__event_emitter__
                    )
                    continue
                    
            # Step 3: Rank by number of keyword matches
            matches.sort(reverse=True, key=lambda x: x[0])
            top_matches = matches[:max_results]
            
            # Step 4: Format results
            results = []
            for score, scholar in top_matches:
                try:
                    profile = scholar.get("profile", {})
                    match_data = {
                        "name": profile.get("name", "N/A"),
                        "department": profile.get("department", "N/A"),
                        "position": profile.get("position", "N/A"),
                        "profile_url": profile.get("url", "N/A"),
                        "match_score": score,
                        "teaching_interests": profile.get("teaching_interests", "N/A"),
                        "recent_publications": [
                            pub.get("title", "N/A")
                            for pub in scholar.get("publications", {}).get("recent", [])[:2]
                        ],
                        "recent_grants": [
                            grant.get("title", "N/A")
                            for grant in scholar.get("grants", {}).get("list", [])[:2]
                        ]
                    }
                    results.append(match_data)
                except Exception as e:
                    await self._emit_status(
                        f"Error formatting match data: {str(e)}",
                        status="warning",
                        __event_emitter__=__event_emitter__
                    )
                    continue
                
            await self._emit_status(
                f"Found {len(matches)} matches, returning top {len(top_matches)}",
                status="complete",
                done=True,
                __event_emitter__=__event_emitter__
            )
            
            return json.dumps({
                "type": "expertise_search_results",
                "status": "success",
                "message": f"Found {len(matches)} matches for expertise in {', '.join(keywords)}",
                "results": results
            }, indent=2)
            
        except Exception as e:
            error_response = {
                "type": "expertise_search_results",
                "status": "error",
                "message": f"Error during expertise search: {str(e)}",
                "results": []
            }
            await self._emit_status(
                f"Error during expertise search: {str(e)}",
                status="error",
                done=True,
                __event_emitter__=__event_emitter__
            )
            return json.dumps(error_response, indent=2)

"""
Example usage:

import asyncio
from uab_scholars_tool import Tools

# Create tool instance
tool = Tools()

# Example 1: Search for a faculty member and get their profile and publications
async def search_faculty():
    result = await tool.search_scholars("Andrea Cherrington")
    print(result)

# Example 2: Count faculty in a department
count = tool.count_faculty_in_department("Preventive Medicine")
print(f"Faculty in Preventive Medicine: {count}")

# Example 3: Get all faculty in a department
async def get_department_faculty():
    result = await tool.get_faculty_list("Anesthesiology")
    print(result)

# Example 4: Get a specific faculty member by ID
async def get_faculty_by_id():
    result = await tool.get_scholar_by_id("450")
    print(result)

# Run async examples:
# asyncio.run(search_faculty())
# asyncio.run(get_department_faculty())
# asyncio.run(get_faculty_by_id())
""" 