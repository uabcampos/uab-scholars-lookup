#!/usr/bin/env python3

from uab_scholars_tool import Tools
import json
import asyncio

async def test_faculty_publications(name: str):
    """Test searching for a faculty member and retrieving their publications."""
    tool = Tools()
    
    print(f"\nSearching for faculty member: {name}")
    print("Retrieving profile and publications...")
    
    # Search for the faculty member
    results = await tool.search_scholars(name)
    data = json.loads(results)
    
    if not data:  # Check if the list is empty
        print("No matching faculty member found")
        return
        
    scholar = data[0]  # Get the first result
    profile = scholar.get("profile", {})
    publications = scholar.get("publications", [])
    
    print(f"\nFound: {profile.get('firstName', 'N/A')} {profile.get('lastName', 'N/A')}")
    print(f"Department: {profile.get('department', 'N/A')}")
    print(f"Position: {profile.get('positions', 'N/A')}")
    print(f"URL: {scholar.get('url', 'N/A')}")
    
    print(f"\nPublications ({len(publications)}):")
    # Show last 3 publications
    for i, pub in enumerate(publications[:3], 1):
        print(f"\n{i}. {pub.get('title', 'N/A')}")
        print(f"   Journal: {pub.get('journal', 'N/A')}")
        print(f"   Year: {pub.get('year', 'N/A')}")
        print(f"   Authors: {pub.get('authors', 'N/A')}")
        if pub.get('doi'):
            print(f"   DOI: {pub['doi']}")
    
    if len(publications) > 3:
        print(f"\n... and {len(publications) - 3} more publications")

async def main():
    # Test with Ryan Melvin
    await test_faculty_publications("Ryan Melvin")

if __name__ == "__main__":
    asyncio.run(main()) 