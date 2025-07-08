#!/usr/bin/env python3
"""
Diagnostic test for UAB Scholars API connection
"""

import requests
import json
import sys

def test_api_connection():
    """Basic test to verify API connectivity and response format"""
    print("Testing UAB Scholars API connection...")
    
    # API endpoint for user search
    url = "https://scholars.uab.edu/api/users"
    
    # Headers
    headers = {
        "User-Agent": "UAB-Scholars-API-Tool/1.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    
    # Try a simple search for "Cherrington"
    payload = {
        "params": {
            "by": "text",
            "type": "user",
            "text": "Cherrington"
        }
    }
    
    try:
        # Make the request
        print("Sending request to UAB Scholars API...")
        response = requests.post(url, json=payload, headers=headers)
        
        # Check status code
        print(f"Status code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error: Received non-200 status code: {response.status_code}")
            print(f"Response content: {response.text}")
            return False
        
        # Try to parse JSON
        try:
            data = response.json()
            
            # Print basic info about the response
            items = data.get("items", [])
            print(f"Response contains {len(items)} items")
            
            if items:
                # Show the first result
                first_item = items[0]
                print("\nFirst result details:")
                print(f"  Name: {first_item.get('firstName', 'Unknown')} {first_item.get('lastName', 'Unknown')}")
                print(f"  Object ID: {first_item.get('objectId', 'Unknown')}")
                print(f"  Discovery URL ID: {first_item.get('discoveryUrlId', 'Unknown')}")
                
                # Try to fetch full user profile
                user_id = first_item.get('objectId')
                if user_id:
                    print(f"\nFetching full profile for ID {user_id}...")
                    user_url = f"https://scholars.uab.edu/api/users/{user_id}"
                    user_response = requests.get(user_url, headers=headers)
                    
                    if user_response.status_code == 200:
                        user_data = user_response.json()
                        print("Successfully retrieved full profile")
                        email = user_data.get("emailAddress", {}).get("address", "No email")
                        print(f"  Email: {email}")
                        
                        positions = user_data.get("positions", [])
                        if positions:
                            print("  Positions:")
                            for pos in positions:
                                dept = pos.get("department", "Unknown department")
                                position = pos.get("position", "Unknown position")
                                print(f"    - {position} in {dept}")
                    else:
                        print(f"Error fetching user profile: {user_response.status_code}")
                
                # Now try a direct search for "Andrea Cherrington"
                direct_payload = {
                    "params": {
                        "by": "text",
                        "type": "user",
                        "text": "Andrea Cherrington"
                    }
                }
                print("\nTrying direct search for 'Andrea Cherrington'...")
                direct_response = requests.post(url, json=direct_payload, headers=headers)
                
                if direct_response.status_code == 200:
                    direct_data = direct_response.json()
                    direct_items = direct_data.get("items", [])
                    print(f"Found {len(direct_items)} results for 'Andrea Cherrington'")
                    
                    for item in direct_items:
                        print(f"  - {item.get('firstName', '')} {item.get('lastName', '')}, ID: {item.get('objectId', '')}")
                else:
                    print(f"Error with direct search: {direct_response.status_code}")
                
                # Try searching by ID 450 (which should be Andrea Cherrington)
                print("\nTrying to fetch user ID 450 directly...")
                id_url = "https://scholars.uab.edu/api/users/450"
                id_response = requests.get(id_url, headers=headers)
                
                if id_response.status_code == 200:
                    id_data = id_response.json()
                    print(f"Found user with ID 450: {id_data.get('firstName', '')} {id_data.get('lastName', '')}")
                else:
                    print(f"Error fetching user ID 450: {id_response.status_code}")
                    
            else:
                print("No items found in the response. API may be responding with empty results.")
                print(f"Full response: {json.dumps(data, indent=2)}")
                
            return True
            
        except json.JSONDecodeError:
            print(f"Error: Could not parse response as JSON")
            print(f"Response content: {response.text[:500]}...")  # Print first 500 chars
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to API: {e}")
        return False
        
    return True

if __name__ == "__main__":
    success = test_api_connection()
    print("\nTest completed.")
    if success:
        print("API connection test successful.")
        sys.exit(0)
    else:
        print("API connection test failed.")
        sys.exit(1) 