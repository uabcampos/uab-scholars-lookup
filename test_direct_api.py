#!/usr/bin/env python3
"""
Simple direct test of the UAB Scholars API without using the tool
"""

import requests
import json
import time
import unicodedata

# Use a session for better connection handling
session = requests.Session()

# Base URL and headers matching the working implementation
BASE_URL = "https://scholars.uab.edu/api"
HEADERS = {
    "Accept": "application/json, text/html, */*",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0"
}

def clean_text(s: str) -> str:
    """Normalize unicode, replace mojibake and fancy punctuation, collapse whitespace."""
    if not isinstance(s, str):
        return ""
    t = unicodedata.normalize("NFKC", s)
    t = t.replace("‚Äì", "-")
    for orig, repl in [
        ("\u2013", "-"), ("\u2014", "-"),
        (""", '"'), (""", '"'),
        ("'", "'"), ("'", "'"),
    ]:
        t = t.replace(orig, repl)
    return " ".join(t.split())

def get_name_variations(full_name: str) -> list:
    """Generate variations of a name to try different formats."""
    parts = full_name.split()
    first, last = parts[0], parts[-1]
    variations = [(first, last)]
    
    # Common name variations
    name_map = {
        "Jim": "James J.",
        "Kristen Allen-Watts": "Kristen Allen Watts",
        "Alex": "Alexander",
        "RJ": "Reaford J.",
        "Bill": "William L.",
        "Stan": "F. Stanford",
        "Matt": "Matthew",
        "Robert": "Robert A.",
        "Terry": "Terrence M.",
        "Ben": "Benjamin",
        "Yu-Mei": "Yu Mei"
    }
    
    if full_name in name_map:
        alt_name = name_map[full_name]
        alt_parts = alt_name.split()
        if len(alt_parts) > 1:
            variations.append((alt_parts[0], alt_parts[-1]))
            if len(alt_parts) > 2:
                variations.append((f"{alt_parts[0]} {alt_parts[1]}", alt_parts[-1]))
        else:
            variations.append((alt_name, last))
    
    if "-" in full_name:
        no_hyphen = full_name.replace("-", " ")
        no_hyphen_parts = no_hyphen.split()
        variations.append((no_hyphen_parts[0], no_hyphen_parts[-1]))
        if len(no_hyphen_parts) > 2:
            variations.append((no_hyphen_parts[0], f"{no_hyphen_parts[-2]} {no_hyphen_parts[-1]}"))
    
    if "Jr" in last or "Sr" in last:
        base_last = last.replace("Jr", "").replace("Sr", "").strip()
        variations.append((first, base_last))
        variations.append((first, f"{base_last}, Jr."))
        variations.append((first, f"{base_last}, Sr."))
        if len(parts) > 2:
            variations.append((f"{first} {parts[1]}", base_last))
            variations.append((f"{first} {parts[1]}", f"{base_last}, Jr."))
            variations.append((f"{first} {parts[1]}", f"{base_last}, Sr."))
    
    if len(parts) > 2 and len(parts[-2]) == 1:
        variations.append((f"{first} {parts[-2]}", last))
    
    return variations

def find_disc_id(full_name: str) -> str:
    """Try to find a user's discoveryUrlId using various name formats."""
    variations = get_name_variations(full_name)
    
    for first, last in variations:
        payload = {"params": {"by": "text", "type": "user", "text": f"{first} {last}"}}
        r = session.post(f"{BASE_URL}/users", json=payload, headers=HEADERS, timeout=15)
        r.raise_for_status()
        
        for u in r.json().get("resource", []):
            # Check if either the exact match or a close match
            if (u.get("firstName","").lower() == first.lower() and
                u.get("lastName","").lower() == last.lower()):
                return u.get("discoveryUrlId")
            
            # Also check if the last name matches and first name is a variation
            if (u.get("lastName","").lower() == last.lower() and
                (u.get("firstName","").lower().startswith(first.lower()) or
                 first.lower().startswith(u.get("firstName","").lower()))):
                return u.get("discoveryUrlId")
    
    return None

def test_search(name: str):
    """Test searching for a scholar by name."""
    print(f"\nTesting search for: {name}")
    
    # First try to find the discovery URL ID
    disc_id = find_disc_id(name)
    if not disc_id:
        print("No matching scholar found")
        return
    
    print(f"Found discovery URL ID: {disc_id}")
    
    # Get full profile
    try:
        profile_url = f"{BASE_URL}/users/{disc_id}"
        response = session.get(profile_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        profile_data = response.json()
        
        print("\nProfile found:")
        print(f"Name: {profile_data.get('firstName', '')} {profile_data.get('lastName', '')}")
        print(f"Department: {profile_data.get('positions', [{}])[0].get('department', 'N/A')}")
        print(f"Email: {profile_data.get('emailAddress', {}).get('address', 'N/A')}")
        print(f"URL: https://scholars.uab.edu/display/{disc_id}")
        
    except Exception as e:
        print(f"Error fetching profile: {str(e)}")

def main():
    # Test 1: Direct ID lookup
    print("\nTest 1: Direct ID lookup for Andrea Cherrington (ID: 450)")
    try:
        response = session.get(f"{BASE_URL}/users/450", headers=HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
        print(f"Status: {response.status_code}")
        print(f"Name: {data.get('firstName', '')} {data.get('lastName', '')}")
        print(f"Department: {data.get('positions', [{}])[0].get('department', 'N/A')}")
    except Exception as e:
        print(f"Error: {str(e)}")
    
    # Test 2: Search by name variations
    test_search("Andrea Cherrington")
    test_search("Andrea L Cherrington")
    test_search("James J. Shaneyfelt")
    test_search("Terrence M. Shaneyfelt")

if __name__ == "__main__":
    main() 