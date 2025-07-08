import requests
import json
import urllib3
from pprint import pprint

# Disable SSL verification warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def clean_name(name):
    # Remove any special characters and extra spaces
    import re
    # Replace hyphens with spaces
    name = name.replace('-', ' ')
    # Remove other special characters
    name = re.sub(r'[^\w\s]', '', name)
    return name.strip()

def get_name_variations(full_name):
    """Generate variations of a name for searching."""
    parts = full_name.split()
    if not parts:
        return []
    
    variations = []
    # Try first + last
    variations.append((parts[0], parts[-1]))
    # Try first initial + last
    variations.append((parts[0][0], parts[-1]))
    
    # Handle compound last names
    if len(parts) > 2:
        # Try first + last (ignoring middle)
        variations.append((parts[0], parts[-1]))
        # Try first + middle + last
        variations.append((parts[0], " ".join(parts[1:])))
        # Try first + last two parts (for compound last names)
        variations.append((parts[0], f"{parts[-2]} {parts[-1]}"))
        # Try first initial + last two parts
        variations.append((parts[0][0], f"{parts[-2]} {parts[-1]}"))
    
    # For hyphenated names, also try without the hyphen
    if '-' in full_name:
        no_hyphen = full_name.replace('-', '')
        parts = no_hyphen.split()
        variations.append((parts[0], parts[-1]))
        variations.append((parts[0][0], parts[-1]))
        if len(parts) > 2:
            variations.append((parts[0], f"{parts[-2]} {parts[-1]}"))
    
    return variations

def debug_faculty_search(name, known_id=None):
    print(f"\n{'='*80}")
    print(f"Debugging faculty member: {name}")
    print(f"{'='*80}")
    
    # Split the name into first and last name
    name_parts = name.split(',')
    if len(name_parts) != 2:
        print(f"Invalid name format: {name}")
        return
    
    last_name, first_name = name_parts
    last_name = clean_name(last_name)
    first_name = clean_name(first_name)
    
    print(f"\nCleaned names:")
    print(f"Last name: '{last_name}'")
    print(f"First name: '{first_name}'")
    
    headers = {
        "User-Agent": "UAB-Scholars-Tool/1.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    
    # Try searching with just the first name
    print(f"\nTrying search with first name: {first_name}")
    try:
        payload = {"params": {"by": "text", "type": "user", "text": first_name}}
        print(f"API payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(
            "https://scholars.uab.edu/api/users",
            json=payload,
            headers=headers,
            verify=False
        )
        print(f"API response status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\nAPI response data:")
            pprint(data)
            
            if data.get("resource"):
                print(f"\nFound {len(data['resource'])} potential matches:")
                for user in data.get("resource", []):
                    user_first = user.get("firstName", "").lower()
                    user_last = user.get("lastName", "").lower()
                    print(f"\nChecking user: {user_first} {user_last}")
                    print(f"User data:")
                    pprint(user)
                    
                    # Check if the last name matches
                    if user_last == last_name.lower():
                        print("Found match by first name + last name match!")
                        return user
    except Exception as e:
        print(f"Error searching with first name: {str(e)}")
    
    # Try searching with just the last name
    print(f"\nTrying search with last name: {last_name}")
    try:
        payload = {"params": {"by": "text", "type": "user", "text": last_name}}
        print(f"API payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(
            "https://scholars.uab.edu/api/users",
            json=payload,
            headers=headers,
            verify=False
        )
        print(f"API response status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\nAPI response data:")
            pprint(data)
            
            if data.get("resource"):
                print(f"\nFound {len(data['resource'])} potential matches:")
                for user in data.get("resource", []):
                    user_first = user.get("firstName", "").lower()
                    user_last = user.get("lastName", "").lower()
                    print(f"\nChecking user: {user_first} {user_last}")
                    print(f"User data:")
                    pprint(user)
                    
                    # Check if the first name matches
                    if user_first == first_name.lower():
                        print("Found match by last name + first name match!")
                        return user
    except Exception as e:
        print(f"Error searching with last name: {str(e)}")
    
    # Try searching with full name
    print(f"\nTrying search with full name: {first_name} {last_name}")
    try:
        payload = {"params": {"by": "text", "type": "user", "text": f"{first_name} {last_name}"}}
        print(f"API payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(
            "https://scholars.uab.edu/api/users",
            json=payload,
            headers=headers,
            verify=False
        )
        print(f"API response status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\nAPI response data:")
            pprint(data)
            
            if data.get("resource"):
                print(f"\nFound {len(data['resource'])} potential matches:")
                for user in data.get("resource", []):
                    user_first = user.get("firstName", "").lower()
                    user_last = user.get("lastName", "").lower()
                    print(f"\nChecking user: {user_first} {user_last}")
                    print(f"User data:")
                    pprint(user)
                    
                    # Check if either name matches
                    if (user_first == first_name.lower() or user_last == last_name.lower()):
                        print("Found match by full name search!")
                        return user
    except Exception as e:
        print(f"Error searching with full name: {str(e)}")
    
    print(f"\nNo matches found for {name}")

def main():
    # List of faculty to debug
    faculty_to_debug = [
        "Cedillo, Yenni",
        "Chandler-Laney, Paula",
        "Chen, Yu-Ying",
        "Foster, Christy",
        "Lai, Byron",
        "Li, Jing",
        "McGinnis, Heather Austin",
        "Palmer, Kelly",
        "Pekmezi, Dorothy W",
        "Shikany, James M"
    ]
    
    for faculty in faculty_to_debug:
        debug_faculty_search(faculty)
        input("\nPress Enter to continue to next faculty member...")

if __name__ == "__main__":
    main() 