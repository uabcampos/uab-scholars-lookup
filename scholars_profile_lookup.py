#!/usr/bin/env python3
"""
Fetch complete profile data for CDTR members from UAB Scholars API.
This script retrieves all available information including profile, grants, publications,
and other professional activities for each member listed in the CSV file.
"""

import json
import requests
import csv
import argparse
from datetime import datetime
from typing import Dict, List, Any, Optional
import scholars_api_shim  # noqa: F401

# API Constants
API_BASE = "https://scholars.uab.edu/api"
USERS_API_BASE = f"{API_BASE}/users"
USERS_API_SEARCH = f"{API_BASE}/users"
PUBS_API_URL = f"{API_BASE}/publications/linkedTo"
GRANTS_API_URL = f"{API_BASE}/grants/linkedTo"
TEACH_API_URL = f"{API_BASE}/teachingActivities/linkedTo"
PROF_ACTIVITIES_API_URL = f"{API_BASE}/professionalActivities/linkedTo"

# API Headers
HEADERS = {
    "User-Agent": "UAB-Scholars-Tool/1.0",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

# Manual overrides for known IDs
MANUAL_DISCOVERY_IDS = {
    'Allen Watts, Kristen': '12139-kristen-allen-watts',
    'Cedillo, Yenni': '17388-yenni-cedillo-juarez',
    # Add more overrides here if needed
}

# Pagination settings
PER_PAGE = 500

def get_name_variations(name: str) -> List[str]:
    """Generate variations of a name for searching."""
    # Only generate variations if not a manual override
    if name in MANUAL_DISCOVERY_IDS:
        return []
    
    # Split name into components
    name_parts = name.split(',')
    if len(name_parts) != 2:
        print(f"Invalid name format for {name}. Expected 'Last, First' format.")
        return []
    
    last_name = name_parts[0].strip()
    first_name = name_parts[1].strip()
    
    # Split first name into parts (e.g., "John A" -> ["John", "A"])
    first_parts = first_name.split()
    
    variations = []
    
    # Add first name then last name
    variations.append(f"{first_name} {last_name}")
    
    # Add first initial then last name
    if first_parts:
        variations.append(f"{first_parts[0][0]} {last_name}")
    
    return variations

def search_user(name: str) -> Optional[str]:
    """Search for a user by name and return their ID if found."""
    # Check for manual override first
    if name in MANUAL_DISCOVERY_IDS:
        return MANUAL_DISCOVERY_IDS[name]
    
    # Get name variations
    name_variations = get_name_variations(name)
    if not name_variations:
        return None
    
    # Try each variation
    for variation in name_variations:
        print(f"Trying variation: {variation}")
        payload = {
            "params": {
                "by": "text",
                "type": "user",
                "text": variation
            }
        }
        
        response = requests.post(USERS_API_SEARCH, json=payload, headers=HEADERS)
        if response.status_code != 200:
            print(f"Error searching for user {variation}: {response.status_code}")
            continue
        
        data = response.json()
        if not data or not isinstance(data, dict):
            print(f"Unexpected response format when searching for {variation}")
            continue
        
        users = data.get('resource', [])
        if not users:
            print(f"No users found for {variation}")
            continue
        
        # Check for exact matches in first and last name
        for user in users:
            user_first = user.get('firstName', '').lower()
            user_last = user.get('lastName', '').lower()
            
            # Get the first and last name from our search variation
            search_parts = variation.lower().split()
            if len(search_parts) >= 2:
                search_first = search_parts[0]
                search_last = search_parts[-1]
                
                # Check for exact match or first name starts with search term
                if (user_last == search_last and 
                    (user_first == search_first or 
                     user_first.startswith(search_first) or 
                     search_first.startswith(user_first))):
                    return user.get('objectId')
        
        print(f"No exact matches found for {variation}")
    
    print(f"Could not find user ID for any variation of {name}")
    return None

def fetch_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    """Fetch user profile data."""
    url = f"{USERS_API_BASE}/{user_id}"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    print(f"Error fetching user profile: {response.status_code}")
    return None

def fetch_linked_data(url: str, user_id: str, object_type: str) -> List[Dict[str, Any]]:
    """Fetch all pages of linked data (publications, grants, etc.)."""
    all_data = []
    start_from = 0
    
    while True:
        payload = {
            "objectId": user_id,
            "objectType": object_type,
            "pagination": {
                "perPage": PER_PAGE,
                "startFrom": start_from
            },
            "favouritesFirst": True,
            "sort": "dateDesc"
        }
        
        response = requests.post(url, json=payload, headers=HEADERS)
        if response.status_code != 200:
            print(f"Error fetching data from {url}: {response.status_code}")
            break
        data = response.json()
        if not data or not isinstance(data, dict):
            print(f"Unexpected response format from {url}")
            break
        # Extract the items from the response
        items = data.get('resource', [])
        if not items:
            break
        all_data.extend(items)
        if len(items) < PER_PAGE:
            break
        start_from += PER_PAGE
    return all_data

def fetch_complete_profile(user_id: str) -> Dict[str, Any]:
    """Fetch complete profile data including all linked information."""
    # Fetch basic profile
    profile = fetch_user_profile(user_id)
    if not profile:
        return {}
    
    # Fetch all linked data
    publications = fetch_linked_data(PUBS_API_URL, user_id, "user")
    grants = fetch_linked_data(GRANTS_API_URL, user_id, "user")
    teaching = fetch_linked_data(TEACH_API_URL, user_id, "user")
    prof_activities = fetch_linked_data(PROF_ACTIVITIES_API_URL, user_id, "user")
    
    # Compile complete profile
    complete_profile = {
        "profile": profile,
        "publications": publications,
        "grants": grants,
        "teaching_activities": teaching,
        "professional_activities": prof_activities,
        "last_updated": datetime.now().isoformat()
    }
    
    return complete_profile

def process_csv(csv_file: str, output_dir: str):
    """Process the CSV file and fetch profiles for each member."""
    # Create output directory if it doesn't exist
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    # Read names from CSV
    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row['PI Name'].strip('"')  # Remove quotes if present
            print(f"\nProcessing {name}...")
            
            # Search for user
            user_id = search_user(name)
            if not user_id:
                print(f"Could not find user ID for {name}")
                continue
            
            # Fetch complete profile
            profile_data = fetch_complete_profile(user_id)
            if not profile_data:
                print(f"Failed to fetch profile data for {name}")
                continue
            
            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = name.lower().replace(" ", "_").replace(".", "").replace(",", "")
            output_file = f"{output_dir}/{filename}_profile_{timestamp}.json"
            
            # Save as JSON
            with open(output_file, 'w') as f:
                json.dump(profile_data, f, indent=2)
            print(f"Profile data saved to: {output_file}")
            
            # Print summary
            print(f"\nProfile Summary for {name}:")
            print(f"Publications: {len(profile_data['publications'])}")
            print(f"Grants: {len(profile_data['grants'])}")
            print(f"Teaching Activities: {len(profile_data['teaching_activities'])}")
            print(f"Professional Activities: {len(profile_data['professional_activities'])}")

def main():
    """Main function to process CSV file and fetch profiles."""
    parser = argparse.ArgumentParser(description='Fetch UAB Scholars profiles for CDTR members.')
    parser.add_argument('--csv', required=True, help='Path to CSV file containing member names')
    parser.add_argument('--output-dir', default='scholar_data', help='Directory to save profile data')
    args = parser.parse_args()
    
    process_csv(args.csv, args.output_dir)

if __name__ == "__main__":
    main() 