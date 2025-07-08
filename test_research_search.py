import asyncio
from uab_scholars_tool import Tools
import json

async def test_expertise_search():
    """Test scanning all scholars by ID and filtering by expertise keywords."""
    tool = Tools()
    
    # User-provided topic keywords
    topic_keywords = [
        "behavioral intervention",
        "digital coaching",
        "mobile health",
        "e-health"
    ]
    
    print("\nThis search will scan the UAB Scholars database for expertise in:", ', '.join(topic_keywords))
    print("This may take several minutes.\n")
    # For demo, limit to first 50 scholars
    start_id = 1
    end_id = 500
    print(f"Proceeding with user IDs {start_id} to {end_id} for a comprehensive search.\n")

    # Step 1: Scan all scholars by ID
    all_scholars = await tool.scan_all_scholars_by_id(start_id=start_id, end_id=end_id)
    print(f"Pulled {len(all_scholars)} scholars.\n")

    # Step 2: Aggregate expertise and filter by topic
    matches = []
    for scholar in all_scholars:
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
        match_count = sum(kw.lower() in expertise_text for kw in topic_keywords)
        if match_count > 0:
            matches.append((match_count, scholar))
    # Step 3: Rank by number of keyword matches
    matches.sort(reverse=True, key=lambda x: x[0])
    top_matches = matches[:3]

    # Step 4: Present results
    print(f"Top {len(top_matches)} matches for expertise in {', '.join(topic_keywords)}:\n")
    for idx, (score, scholar) in enumerate(top_matches, 1):
        profile = scholar.get("profile", {})
        print(f"{idx}. {profile.get('name', 'N/A')} ({profile.get('department', 'N/A')})")
        print(f"   Position: {profile.get('position', 'N/A')}")
        print(f"   Profile: {profile.get('url', 'N/A')}")
        print(f"   Matched on {score} topic(s)")
        # Show why they matched
        print("   Example expertise:")
        print(f"      Teaching: {profile.get('teaching_interests', 'N/A')}")
        pubs = scholar.get("publications", {}).get("recent", [])
        if pubs:
            print(f"      Recent Publication: {pubs[0].get('title', 'N/A')}")
        grants = scholar.get("grants", {}).get("list", [])
        if grants:
            print(f"      Recent Grant: {grants[0].get('title', 'N/A')}")
        print()
    if not top_matches:
        print("No matches found for the provided expertise keywords.")

if __name__ == "__main__":
    asyncio.run(test_expertise_search()) 