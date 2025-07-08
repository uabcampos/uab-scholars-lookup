#!/usr/bin/env python3
"""
Simple test for a single method of the UAB Scholars Tool
"""

import asyncio
import json
from uab_scholars_tool import Tools

async def test_specific_scholar():
    """Test with a specific scholar ID"""
    tools = Tools()
    
    print("Testing lookup of Jing Li (ID: 19733)")
    
    # Option to disable some data for faster testing
    tools.valves.include_teaching = False
    
    result = await tools.get_scholar_by_id("19733")
    data = json.loads(result)
    
    if data and data.get('profile'):
        profile = data['profile']
        print(f"Success! Found {profile['firstName']} {profile['lastName']}")
        print(f"Department: {profile['department']}")
        print(f"Publications: {len(data['publications'])}")
        print(f"Grants: {len(data['grants'])}")
    else:
        print("Failed to find scholar")

if __name__ == "__main__":
    asyncio.run(test_specific_scholar()) 