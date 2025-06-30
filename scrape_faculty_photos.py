import requests
import json
import urllib3
import os
import base64
from pprint import pprint
import scholars_api_shim  # noqa: F401

# Disable SSL verification warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def create_directory(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

def clean_name(name):
    # Remove any special characters and extra spaces
    import re
    # Replace hyphens with spaces
    name = name.replace('-', ' ')
    # Remove other special characters
    name = re.sub(r'[^\w\s]', '', name)
    return name.strip()

def get_faculty_id(name):
    # Split the name into first and last name
    name_parts = name.split(',')
    if len(name_parts) != 2:
        print(f"Invalid name format: {name}")
        return None
    
    last_name, first_name = name_parts
    last_name = clean_name(last_name)
    first_name = clean_name(first_name)
    
    headers = {
        "User-Agent": "UAB-Scholars-Tool/1.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    
    # Try searching with just the first name
    try:
        payload = {"params": {"by": "text", "type": "user", "text": first_name}}
        response = requests.post(
            "https://scholars.uab.edu/api/users",
            json=payload,
            headers=headers,
            verify=False
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("resource"):
                for user in data.get("resource", []):
                    user_first = user.get("firstName", "").lower()
                    user_last = user.get("lastName", "").lower()
                    
                    # Check if the last name matches
                    if user_last == last_name.lower():
                        return user.get("objectId")
    except Exception as e:
        print(f"Error searching with first name: {str(e)}")
    
    # Try searching with just the last name
    try:
        payload = {"params": {"by": "text", "type": "user", "text": last_name}}
        response = requests.post(
            "https://scholars.uab.edu/api/users",
            json=payload,
            headers=headers,
            verify=False
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("resource"):
                for user in data.get("resource", []):
                    user_first = user.get("firstName", "").lower()
                    user_last = user.get("lastName", "").lower()
                    
                    # Check if the first name matches
                    if user_first == first_name.lower():
                        return user.get("objectId")
    except Exception as e:
        print(f"Error searching with last name: {str(e)}")
    
    # Try searching with full name
    try:
        payload = {"params": {"by": "text", "type": "user", "text": f"{first_name} {last_name}"}}
        response = requests.post(
            "https://scholars.uab.edu/api/users",
            json=payload,
            headers=headers,
            verify=False
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("resource"):
                for user in data.get("resource", []):
                    user_first = user.get("firstName", "").lower()
                    user_last = user.get("lastName", "").lower()
                    
                    # Check if either name matches
                    if (user_first == first_name.lower() or user_last == last_name.lower()):
                        return user.get("objectId")
    except Exception as e:
        print(f"Error searching with full name: {str(e)}")
    
    return None

def get_faculty_photo(object_id):
    headers = {
        "User-Agent": "UAB-Scholars-Tool/1.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    
    try:
        response = requests.get(
            f"https://scholars.uab.edu/api/users/{object_id}/photo",
            headers=headers,
            verify=False
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("thumbnail"):
                return data["thumbnail"]
    except Exception as e:
        print(f"Error getting photo: {str(e)}")
    
    return None

def save_base64_image(base64_data, output_path):
    try:
        # Remove the data URL prefix if present
        if ',' in base64_data:
            base64_data = base64_data.split(',')[1]
        
        # Decode the base64 data
        image_data = base64.b64decode(base64_data)
        
        # Save the image
        with open(output_path, 'wb') as f:
            f.write(image_data)
        
        return True
    except Exception as e:
        print(f"Error saving image: {str(e)}")
        return False

def main():
    # Create output directory
    output_dir = "faculty_photos"
    create_directory(output_dir)
    
    # Read faculty names from CSV
    total_faculty = 0
    images_saved = 0
    skipped_faculty = []
    
    try:
        with open("cdtr members.csv", "r") as f:
            for line in f:
                name = line.strip()
                if not name:
                    continue
                
                total_faculty += 1
                print(f"\nProcessing: {name}")
                
                # Get faculty ID
                object_id = get_faculty_id(name)
                if not object_id:
                    print(f"Could not find ID for {name}")
                    skipped_faculty.append((name, "Could not find ID"))
                    continue
                
                # Get photo
                photo_data = get_faculty_photo(object_id)
                if not photo_data:
                    print(f"No photo found for {name}")
                    skipped_faculty.append((name, "No photo found"))
                    continue
                
                # Create output filename
                name_parts = name.split(',')
                if len(name_parts) != 2:
                    print(f"Invalid name format: {name}")
                    skipped_faculty.append((name, "Invalid name format"))
                    continue
                
                last_name, first_name = name_parts
                last_name = clean_name(last_name)
                first_name = clean_name(first_name)
                output_filename = f"{last_name}_{first_name}.png"
                output_path = os.path.join(output_dir, output_filename)
                
                # Save image
                if save_base64_image(photo_data, output_path):
                    print(f"Saved photo for {name}")
                    images_saved += 1
                else:
                    print(f"Failed to save photo for {name}")
                    skipped_faculty.append((name, "Failed to save image"))
    
    except Exception as e:
        print(f"Error processing CSV: {str(e)}")
    
    # Print summary
    print("\nSummary:")
    print(f"Total faculty processed: {total_faculty}")
    print(f"Images saved: {images_saved}")
    print(f"Faculty skipped: {len(skipped_faculty)}")
    if skipped_faculty:
        print("\nSkipped faculty:")
        for name, reason in skipped_faculty:
            print(f"- {name}: {reason}")

if __name__ == "__main__":
    main() 