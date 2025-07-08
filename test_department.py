#!/usr/bin/env python3

from uab_scholars_tool import Tools
import json
import asyncio

async def test_department_search(department: str):
    """Test searching for faculty in a department."""
    tool = Tools()
    
    print(f"\nSearching for faculty in department: {department}")
    print("Retrieving faculty list...")
    
    # Search for faculty in the department
    results = await tool.search_by_department(department)
    data = json.loads(results)
    
    if not data:  # Check if the list is empty
        print("No faculty found in this department")
        return
        
    print(f"\nFound {len(data)} faculty members:")
    for i, scholar in enumerate(data, 1):
        profile = scholar.get("profile", {})
        print(f"\n{i}. {profile.get('name', 'N/A')}")
        print(f"   Position: {profile.get('position', 'N/A')}")
        print(f"   URL: {profile.get('url', 'N/A')}")
        
        # Show publication count if available
        publications = scholar.get("publications", {})
        if publications:
            print(f"   Publications: {publications.get('total', 0)}")

async def main():
    # Test with Anesthesiology department
    await test_department_search("Anesthesiology")

if __name__ == "__main__":
    asyncio.run(main()) 