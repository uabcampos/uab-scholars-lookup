#!/usr/bin/env python3
"""
Synchronous wrapper test for UAB Scholars Tool
"""

import asyncio
import json
from uab_scholars_tool import Tools

# Create a synchronous wrapper for the tool
class SyncUABScholarsTools:
    def __init__(self):
        self.tools = Tools()
    
    def search_scholars(self, query, department=""):
        """Synchronous wrapper for search_scholars"""
        return asyncio.run(self.tools.search_scholars(query, department))
    
    def get_scholar_by_id(self, scholar_id):
        """Synchronous wrapper for get_scholar_by_id"""
        return asyncio.run(self.tools.get_scholar_by_id(scholar_id))
    
    def search_by_department(self, department):
        """Synchronous wrapper for search_by_department"""
        return asyncio.run(self.tools.search_by_department(department))

def main():
    """Test synchronous usage"""
    sync_tools = SyncUABScholarsTools()
    
    # Set a smaller number of results for testing
    sync_tools.tools.valves.max_results = 2
    
    # Test search by department
    print("Searching for scholars in Preventive Medicine...")
    result = sync_tools.search_by_department("Preventive Medicine")
    data = json.loads(result)
    
    if isinstance(data, list) and data:
        print(f"Found {len(data)} scholars")
        for scholar in data:
            profile = scholar['profile']
            print(f"- {profile['firstName']} {profile['lastName']}")
    else:
        print("No scholars found")

if __name__ == "__main__":
    main() 