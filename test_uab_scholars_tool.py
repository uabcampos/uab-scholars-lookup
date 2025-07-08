#!/usr/bin/env python3
"""
Test script for the UAB Scholars Tool
"""

import asyncio
import json
import traceback
from uab_scholars_tool import Tools

async def print_event(event):
    """Simple event handler that prints events"""
    if event["type"] == "status":
        status = event["data"]["status"]
        desc = event["data"]["description"]
        done = event["data"]["done"]
        print(f"[{status.upper()}] {desc}" + (" ✓" if done else ""))
    elif event["type"] == "citation":
        print(f"[CITATION] {event['data']['source']['name']}")
    else:
        print(f"[EVENT] {event}")

async def test_search_scholars():
    """Test the search_scholars method"""
    print("\n=== Testing search_scholars ===")
    tools = Tools()
    
    # Set to a smaller number for testing
    tools.valves.max_results = 2
    
    # Search for Cherrington which should have more results
    print("Searching for 'Cherrington'...")
    result = await tools.search_scholars("Cherrington", __event_emitter__=print_event)
    
    # Pretty print the first result for easier reading
    data = json.loads(result)
    if isinstance(data, list) and len(data) > 0:
        scholar = data[0]
        print(f"\nFound scholar: {scholar['profile']['firstName']} {scholar['profile']['lastName']}")
        print(f"Department: {scholar['profile']['department']}")
        print(f"Publications: {len(scholar['publications'])}")
        print(f"Grants: {len(scholar['grants'])}")
        print(f"Teaching activities: {len(scholar['teaching_activities'])}")
        return True
    elif isinstance(data, dict) and "results" in data and len(data["results"]) == 0:
        print("No scholars found - API returned empty results list")
        return False
    else:
        print(f"Unexpected response format: {json.dumps(data)[:500]}...")
        return False

async def test_get_scholar_by_id():
    """Test the get_scholar_by_id method"""
    print("\n=== Testing get_scholar_by_id ===")
    tools = Tools()
    
    # Get Andrea Cherrington by ID (450)
    print("Fetching scholar with ID 450...")
    try:
        result = await tools.get_scholar_by_id("450", __event_emitter__=print_event)
        
        # Pretty print some details
        data = json.loads(result)
        if data and data.get('profile'):
            profile = data['profile']
            print(f"\nFound scholar: {profile['firstName']} {profile['lastName']}")
            print(f"Email: {profile['email']}")
            print(f"Department: {profile['department']}")
            print(f"Bio preview: {profile['bio'][:150]}...")
            return True
        elif "error" in data:
            print(f"Error in response: {data['error']}")
            return False
        else:
            print("Schema did not match expected format")
            return False
    except Exception as e:
        print(f"Exception during test: {e}")
        traceback.print_exc()
        return False

async def test_search_by_department():
    """Test the search_by_department method"""
    print("\n=== Testing search_by_department ===")
    tools = Tools()
    
    # Set to a smaller number for testing
    tools.valves.max_results = 3
    
    # Search for scholars in Preventive Medicine
    print("Searching for 'Preventive Medicine' department...")
    result = await tools.search_by_department("Preventive Medicine", __event_emitter__=print_event)
    
    # Pretty print the results count
    try:
        data = json.loads(result)
        if isinstance(data, list) and data:
            print(f"\nFound {len(data)} scholars in 'Preventive Medicine'")
            for scholar in data:
                profile = scholar['profile']
                print(f"- {profile['firstName']} {profile['lastName']}: {profile['positions']}")
            return True
        elif isinstance(data, dict) and "results" in data and len(data["results"]) == 0:
            print("No scholars found in department - API returned empty results list")
            return False
        else:
            print(f"Unexpected response format: {type(data)}")
            return False
    except Exception as e:
        print(f"Exception during test: {e}")
        traceback.print_exc()
        return False

async def main():
    """Run all tests"""
    print("Testing UAB Scholars Tool")
    
    success_count = 0
    test_count = 3
    
    try:
        # Test search by scholar name
        if await test_search_scholars():
            success_count += 1
        
        # Test get scholar by ID
        if await test_get_scholar_by_id():
            success_count += 1
        
        # Test search by department
        if await test_search_by_department():
            success_count += 1
        
        print(f"\nTests completed: {success_count}/{test_count} successful")
        
        if success_count == test_count:
            print("🎉 All tests passed!")
            return 0
        else:
            print(f"❌ Some tests failed ({test_count - success_count} failures)")
            return 1
    except Exception as e:
        print(f"\nUnhandled exception during testing: {e}")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    result = asyncio.run(main())
    import sys
    sys.exit(result) 