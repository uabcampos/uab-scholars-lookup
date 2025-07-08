#!/usr/bin/env python3
# test_grants.py

"""
Test script to verify the grants functionality of the UAB Scholars Tool.
Tests both the grants retrieval and the overall scholar search functionality.
"""

import asyncio
import json
from uab_scholars_tool import Tools

async def test_grants_retrieval():
    """Test grants retrieval for a known faculty member with grants."""
    tool = Tools()
    
    # Test case 1: Direct grants retrieval
    print("\nTest Case 1: Direct grants retrieval")
    print("-----------------------------------")
    disc_id = "450-andrea-cherrington"  # Correct discoveryUrlId for Andrea Cherrington
    print(f"[DEBUG] Using disc_id for direct grants retrieval: {disc_id}")
    grants = await tool._get_grants(disc_id)
    print(f"Retrieved {len(grants)} grants")
    if grants:
        print("\nSample grant:")
        print(json.dumps(grants[0], indent=2))
    
    # Test case 2: Full scholar search with grants
    print("\nTest Case 2: Full scholar search with grants")
    print("-------------------------------------------")
    result = await tool.search_scholars("Andrea Cherrington")
    data = json.loads(result)
    print(f"[DEBUG] search_scholars returned type: {type(data)}")
    if data and isinstance(data, list) and len(data) > 0:
        scholar = data[0]
        print(f"[DEBUG] Scholar profile: {scholar.get('profile', {})}")
        grants = scholar.get("grants", {})
        print(f"Total grants: {grants.get('total', 0)}")
        if grants.get("list"):
            print("\nSample grant from search:")
            print(json.dumps(grants["list"][0], indent=2))
    
    # Test case 3: Get scholar by ID with grants
    print("\nTest Case 3: Get scholar by ID with grants")
    print("----------------------------------------")
    scholar_id = "450"  # Correct numeric ID for Andrea Cherrington
    print(f"[DEBUG] Using scholar_id for get_scholar_by_id: {scholar_id}")
    result = await tool.get_scholar_by_id(scholar_id)
    data = json.loads(result)
    print(f"[DEBUG] get_scholar_by_id returned keys: {list(data.keys())}")
    grants = data.get("grants", [])
    print(f"Total grants: {len(grants)}")
    if grants:
        print("\nSample grant from ID lookup:")
        print(json.dumps(grants[0], indent=2))

def is_diabetes_related(grant):
    diabetes_keywords = [
        "diabetes", "diabetic", "glucose", "insulin", "metabolic",
        "obesity", "weight", "glycemic", "HbA1c", "A1C"
    ]
    title = grant.get("title", "").lower()
    description = grant.get("description", "").lower()
    labels = "; ".join(l.get("value", "") for l in grant.get("labels", [])).lower()
    text = f"{title} {description} {labels}"
    return any(keyword in text for keyword in diabetes_keywords)

def get_recent_diabetes_grants(grants, limit=3):
    diabetes_grants = [g for g in grants if is_diabetes_related(g)]
    return sorted(
        diabetes_grants,
        key=lambda x: x.get("date1", {}).get("year", 0),
        reverse=True
    )[:limit]

def main():
    """Run all tests."""
    print("Starting grants functionality tests...")
    asyncio.run(test_grants_retrieval())
    print("\nTests completed.")

    # Load Gareth Dutton's JSON data
    with open('biosketches/biosketch_Dutton_Gareth_20250602_145116.json', 'r') as f:
        data = json.load(f)
    
    # Extract all grants
    all_grants = data.get("recent_diabetes_grants", [])
    
    # Debug: Print all grants and their diabetes-related status
    print("\nAll Grants for Gareth Dutton:")
    for grant in all_grants:
        print(f"Title: {grant.get('title', 'N/A')}")
        print(f"Funder: {grant.get('funderName', 'N/A')}")
        print(f"Year: {grant.get('date1', {}).get('year', 'N/A')}")
        print(f"Is Diabetes Related: {is_diabetes_related(grant)}")
        print("---")
    
    # Get the 3 most recent diabetes-related grants
    recent_grants = get_recent_diabetes_grants(all_grants)
    
    # Display the results
    print("\n3 Most Recent Diabetes-Related Grants for Gareth Dutton:")
    for grant in recent_grants:
        print(f"Title: {grant.get('title', 'N/A')}")
        print(f"Funder: {grant.get('funderName', 'N/A')}")
        print(f"Year: {grant.get('date1', {}).get('year', 'N/A')}")
        print("---")

if __name__ == "__main__":
    main() 