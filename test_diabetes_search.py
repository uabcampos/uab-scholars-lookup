import asyncio
from uab_scholars_tool import Tools
import json

async def test_diabetes_search():
    """Scan all scholars by ID in chunks and filter by diabetes research interests."""
    tool = Tools()
    
    # Search terms for diabetes research
    search_terms = [
        "diabetes",
        "diabetic",
        "type 1 diabetes",
        "type 2 diabetes",
        "gestational diabetes",
        "diabetes mellitus"
    ]
    
    # Parameters for chunked search
    chunk_size = 500
    min_id = 1
    max_id = 6000  # Adjust as needed for your database size
    print(f"\nThis search will scan the UAB Scholars database for research interests in: {', '.join(search_terms)}")
    print(f"Scanning scholar IDs {min_id} to {max_id} in chunks of {chunk_size}...\n")

    all_matches = []
    total_scholars = 0
    for chunk_start in range(min_id, max_id + 1, chunk_size):
        chunk_end = min(chunk_start + chunk_size - 1, max_id)
        print(f"Scanning IDs {chunk_start} to {chunk_end}...")
        scholars = await tool.scan_all_scholars_by_id(start_id=chunk_start, end_id=chunk_end)
        total_scholars += len(scholars)
        # Filter by research interests, publications, grants, and other fields
        for scholar in scholars:
            profile = scholar.get("profile", {})
            text_to_search = " ".join([
                profile.get("research_interests", ""),
                profile.get("department", ""),
                profile.get("position", ""),
                profile.get("bio", ""),
                # Publications
                " ".join(pub.get("title", "") for pub in scholar.get("publications", {}).get("recent", [])),
                # Grants
                " ".join(grant.get("title", "") for grant in scholar.get("grants", {}).get("list", [])),
            ]).lower()
            if any(term.lower() in text_to_search for term in search_terms):
                all_matches.append(scholar)
        print(f"  → Found {len(all_matches)} total matches so far.\n")

    print(f"\nScanned {total_scholars} scholars in total.")
    print(f"Found {len(all_matches)} scholars with diabetes-related research or expertise:\n")
    for idx, scholar in enumerate(all_matches, 1):
        profile = scholar.get("profile", {})
        print(f"{idx}. {profile.get('name', 'N/A')} ({profile.get('department', 'N/A')})")
        print(f"   Position: {profile.get('position', 'N/A')}")
        print(f"   Research Interests: {profile.get('research_interests', 'N/A')}")
        print(f"   Profile: {profile.get('url', 'N/A')}")
        # Show recent publications if available
        pubs = scholar.get("publications", {}).get("recent", [])
        if pubs:
            print("   Recent Publications:")
            for pub in pubs[:2]:
                print(f"      - {pub.get('title', 'N/A')}")
        # Show recent grants if available
        grants = scholar.get("grants", {}).get("list", [])
        if grants:
            print("   Recent Grants:")
            for grant in grants[:2]:
                print(f"      - {grant.get('title', 'N/A')}")
        print()
    if not all_matches:
        print("No matches found for diabetes-related research or expertise.")

if __name__ == "__main__":
    asyncio.run(test_diabetes_search()) 