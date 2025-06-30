#!/usr/bin/env python3
"""
CDTR Collaboration Analysis Tool

This script analyzes diabetes-related publications and collaborations between faculty members
listed in the CDTR_MemberBase_Cleaned.csv file. It searches UAB Scholars for publications
from the last 15 years and identifies collaborative publications between faculty members.
"""

import csv
import json
from datetime import datetime, timedelta
import requests
from typing import Dict, List, Set, Tuple
import asyncio
from collections import defaultdict
import unicodedata
import re
from difflib import SequenceMatcher
import time
import scholars_api_shim  # noqa: F401

# API Configuration
API_BASE = "https://scholars.uab.edu/api"
HEADERS = {
    "Accept": "application/json, text/html, */*",
    "Content-Type": "application/json",
    "User-Agent": "UAB-Scholars-Tool/1.0"
}

# Diabetes-related keywords for filtering publications
DIABETES_KEYWORDS = {
    "diabetes", "diabetic", "glucose", "insulin", "glycemic", "HbA1c", "A1C",
    "type 1 diabetes", "type 2 diabetes", "T1D", "T2D", "prediabetes",
    "metabolic syndrome", "insulin resistance", "diabetes mellitus"
}

class CDTRCollaborationAnalyzer:
    def __init__(self, csv_file: str):
        self.csv_file = csv_file
        self.faculty_list = []
        self.faculty_search_names = []
        self.faculty_ids = {}
        self.collaborations = defaultdict(list)
        self.publication_counts = defaultdict(int)
        self.total_diabetes_pubs = defaultdict(int)  # New dictionary to track total diabetes publications
        self.name_variations_cache = {}
        
    def normalize_name(self, name: str) -> str:
        """Normalize a name by removing special characters and converting to lowercase."""
        # Remove accents and special characters
        name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('ASCII')
        # Convert to lowercase and remove extra spaces
        name = ' '.join(name.lower().split())
        # Remove common suffixes
        name = re.sub(r'\s+(jr\.?|sr\.?|ph\.?d\.?|md\.?|m\.?d\.?|dr\.?)$', '', name)
        return name

    def get_name_variations(self, full_name: str) -> list:
        """
        Generate variations of a name to try different formats.
        Returns a list of (first, last) tuples to try.
        """
        parts = full_name.split()
        first, last = parts[0], parts[-1]
        variations = [(first, last)]  # Start with original format
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
        if len(parts) > 2 and len(parts[-2]) == 1:  # Middle initial
            variations.append((f"{first} {parts[-2]}", last))
        return variations

    def load_faculty_list(self):
        """Load faculty list from CSV file and clean the data."""
        self.faculty_list = []
        self.faculty_search_names = []
        try:
            with open(self.csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['Active Awards'] == 'No active awards':
                        continue
                    name = row['PI Name'].strip().rstrip(',')
                    if not name:
                        continue
                    # Parse to 'First Last' for searching, keep 'Last, First' for display
                    if ',' in name:
                        parts = [p.strip() for p in name.split(',')]
                        if len(parts) == 2:
                            display_name = f"{parts[0]}, {parts[1]}"
                            search_name = f"{parts[1]} {parts[0]}"
                        else:
                            display_name = name
                            search_name = name.replace(',', '')
                    else:
                        display_name = name
                        search_name = name
                    self.faculty_list.append(display_name)
                    self.faculty_search_names.append(search_name)
            print(f"\nLoaded {len(self.faculty_list)} active faculty members")
        except Exception as e:
            print(f"Error loading faculty list: {str(e)}")
            self.faculty_list = [
                "Cherrington, Andrea L",
                "Juarez, Lucia",
                "Presley, Caroline A",
                "Howell, Carrie R"
            ]
            self.faculty_search_names = [
                "Andrea L Cherrington",
                "Lucia Juarez",
                "Caroline A Presley",
                "Carrie R Howell"
            ]

    def is_similar_name(self, author_name, faculty_name):
        # Normalize both names to lowercase
        author_name = author_name.lower()
        faculty_name = faculty_name.lower()

        # Parse author name (e.g., 'L D Juarez' or 'Juarez, Lucia')
        author_parts = author_name.split()
        if ',' in author_name:
            # Format: 'Juarez, Lucia'
            author_last = author_parts[0].strip(',')
            author_first = author_parts[1] if len(author_parts) > 1 else ''
            author_middle = author_parts[2] if len(author_parts) > 2 else ''
        else:
            # Format: 'L D Juarez'
            author_last = author_parts[-1]
            author_first = author_parts[0] if len(author_parts) > 1 else ''
            author_middle = author_parts[1] if len(author_parts) > 2 else ''

        # Parse faculty name (e.g., 'Juarez, Lucia')
        faculty_parts = faculty_name.split(',')
        faculty_last = faculty_parts[0].strip()
        faculty_first_middle = faculty_parts[1].strip().split() if len(faculty_parts) > 1 else []
        faculty_first = faculty_first_middle[0] if faculty_first_middle else ''
        faculty_middle = faculty_first_middle[1] if len(faculty_first_middle) > 1 else ''

        # Compare last names
        if author_last != faculty_last:
            return False

        # Compare initials of first and middle names
        author_first_init = author_first[0] if author_first else ''
        author_middle_init = author_middle[0] if author_middle else ''
        faculty_first_init = faculty_first[0] if faculty_first else ''
        faculty_middle_init = faculty_middle[0] if faculty_middle else ''

        return author_first_init == faculty_first_init and author_middle_init == faculty_middle_init

    async def find_scholar_id(self, search_name: str) -> str:
        API_USERS = f"{API_BASE}/users"
        for first, last in self.get_name_variations(search_name):
            try:
                payload = {"params": {"by": "text", "type": "user", "text": f"{first} {last}"}}
                if "cherrington" in search_name.lower():
                    print(f"[DEBUG] Payload for {search_name}: {payload}")
                response = requests.post(API_USERS, json=payload, headers=HEADERS, timeout=15)
                if "cherrington" in search_name.lower():
                    print(f"[DEBUG] Raw API response for {search_name}: {response.text}")
                response.raise_for_status()
                for user in response.json().get("resource", []):
                    if (user.get("firstName", "").lower() == first.lower() and user.get("lastName", "").lower() == last.lower()):
                        return user.get("discoveryUrlId")
                    if (user.get("lastName", "").lower() == last.lower() and (user.get("firstName", "").lower().startswith(first.lower()) or first.lower().startswith(user.get("firstName", "").lower()))):
                        return user.get("discoveryUrlId")
            except Exception as e:
                print(f"Error searching for {search_name}: {str(e)}")
                continue
        return None

    async def get_publications(self, scholar_id: str) -> List[Dict]:
        """Get publications for a scholar from the last 15 years."""
        try:
            # Calculate date range (15 years ago)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=15*365)
            
            pubs_url = f"{API_BASE}/publications/linkedTo"
            publications = []
            start = 0
            per_page = 100
            
            while True:
                payload = {
                    "objectId": scholar_id,
                    "objectType": "user",
                    "pagination": {"perPage": per_page, "startFrom": start},
                    "favouritesFirst": True,
                    "sort": "dateDesc"
                }
                
                response = requests.post(pubs_url, json=payload, headers=HEADERS)
                response.raise_for_status()
                data = response.json()
                
                results = data.get("resource", [])
                if not results:
                    break
                
                for pub in results:
                    # Check publication date
                    pub_date = pub.get("publicationDate", {})
                    year = pub_date.get("year")
                    if not year or int(year) < start_date.year:
                        continue
                    
                    # Check if publication is diabetes-related
                    title = pub.get("title", "").lower()
                    abstract = pub.get("abstract", "").lower()
                    if not any(keyword.lower() in title or keyword.lower() in abstract 
                             for keyword in DIABETES_KEYWORDS):
                        continue
                    
                    # Get co-authors
                    authors = []
                    for author in pub.get("authors", []):
                        author_name = author.get("fullName", "")
                        if author_name:
                            authors.append(author_name)
                    
                    publications.append({
                        "title": pub.get("title", ""),
                        "year": year,
                        "journal": pub.get("journal", ""),
                        "doi": pub.get("doi", ""),
                        "url": pub.get("url", ""),
                        "authors": authors
                    })
                
                total = data.get("pagination", {}).get("total", 0)
                start += per_page
                if start >= total:
                    break
            
            return publications
            
        except Exception as e:
            print(f"Error getting publications for {scholar_id}: {str(e)}")
            return []

    def find_collaborations(self, publications: List[Dict], scholar_name: str) -> List[Dict]:
        """Find collaborations between faculty members in publications. Debug: print normalization and matching for the example publication."""
        collaborations = []
        normalized_scholar_name = self.normalize_name(scholar_name)
        # Debug: print normalized faculty names
        print("\n[DEBUG] Normalized faculty names:")
        for faculty_name in self.faculty_list:
            print(f"- {faculty_name} => {self.normalize_name(faculty_name)}")
        
        for pub in publications:
            # Only debug the example publication
            if pub["title"].startswith("Associations Between Suboptimal Social Determinants of Health and Diabetes Distress"):
                print("\n[DEBUG] Example publication author normalization and matching:")
                for author in pub["authors"]:
                    normalized_author = self.normalize_name(author)
                    print(f"Author: {author} => {normalized_author}")
                    for faculty_name in self.faculty_list:
                        normalized_faculty = self.normalize_name(faculty_name)
                        sim = self.is_similar_name(normalized_author, normalized_faculty)
                        print(f"  Compare to faculty: {faculty_name} => {normalized_faculty} | Similar: {sim}")
        
        for pub in publications:
            co_authors = []
            for author in pub["authors"]:
                normalized_author = self.normalize_name(author)
                # Skip if it's the same author
                if self.is_similar_name(normalized_author, normalized_scholar_name):
                    continue
                # Check if author is in faculty list using fuzzy matching
                for faculty_name in self.faculty_list:
                    if self.is_similar_name(normalized_author, self.normalize_name(faculty_name)):
                        co_authors.append(faculty_name)
                        break
            if co_authors:
                collaborations.append({
                    "title": pub["title"],
                    "year": pub["year"],
                    "journal": pub["journal"],
                    "doi": pub["doi"],
                    "url": pub["url"],
                    "collaborators": co_authors
                })
        return collaborations

    def export_to_csv(self, output_file: str = "cdtr_collaborations.csv"):
        """Export collaboration results to a CSV file."""
        try:
            with open(output_file, 'w', newline='') as csvfile:
                fieldnames = ['Faculty Member', 'Total Diabetes Publications', 'Collaborative Publications', 
                            'Collaboration Title', 'Year', 'Journal', 'DOI', 'Collaborators']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for faculty_name in self.faculty_list:
                    total_diabetes_pubs = self.total_diabetes_pubs.get(faculty_name, 0)
                    collab_pubs = len(self.collaborations.get(faculty_name, []))
                    
                    # If no collaborations, still write a row with the counts
                    if not self.collaborations.get(faculty_name):
                        writer.writerow({
                            'Faculty Member': faculty_name,
                            'Total Diabetes Publications': total_diabetes_pubs,
                            'Collaborative Publications': collab_pubs,
                            'Collaboration Title': '',
                            'Year': '',
                            'Journal': '',
                            'DOI': '',
                            'Collaborators': ''
                        })
                    else:
                        for collab in self.collaborations.get(faculty_name, []):
                            writer.writerow({
                                'Faculty Member': faculty_name,
                                'Total Diabetes Publications': total_diabetes_pubs,
                                'Collaborative Publications': collab_pubs,
                                'Collaboration Title': collab['title'],
                                'Year': collab['year'],
                                'Journal': collab['journal'],
                                'DOI': collab['doi'],
                                'Collaborators': ', '.join(collab['collaborators'])
                            })
            print(f"\nResults exported to {output_file}")
        except Exception as e:
            print(f"Error exporting to CSV: {str(e)}")

    def is_diabetes_related(self, publication: Dict) -> bool:
        """Check if a publication is diabetes-related based on title and abstract."""
        title = publication.get("title", "").lower()
        abstract = publication.get("abstract", "").lower()
        return any(keyword.lower() in title or keyword.lower() in abstract 
                  for keyword in DIABETES_KEYWORDS)

    def is_same_person(self, author_name: str, faculty_name: str) -> bool:
        """Check if an author name matches a faculty name using normalized comparison."""
        normalized_author = self.normalize_name(author_name)
        normalized_faculty = self.normalize_name(faculty_name)
        return self.is_similar_name(normalized_author, normalized_faculty)

    async def analyze_collaborations(self):
        """Analyze collaborations between faculty members."""
        # Initialize faculty list
        print("Loading faculty list...")
        self.load_faculty_list()
        
        start_time = time.time()
        total_faculty = len(self.faculty_list)
        processed = 0
        
        print(f"\nStarting collaboration analysis for {total_faculty} faculty members...")
        print("=" * 80)
        
        for idx, faculty in enumerate(self.faculty_list):
            processed += 1
            elapsed = time.time() - start_time
            print(f"\n[{processed}/{total_faculty}] Processing {faculty}... (Elapsed: {elapsed:.1f}s)")
            
            # Use the corresponding search name in 'First Last' format
            search_name = self.faculty_search_names[idx]
            scholar_id = await self.find_scholar_id(search_name)
            if not scholar_id:
                print(f"  No scholar ID found for {faculty}")
                continue
                
            # Get publications
            publications = await self.get_publications(scholar_id)
            if not publications:
                print(f"  No publications found for {faculty}")
                continue
                
            # Filter for diabetes-related publications
            diabetes_pubs = [pub for pub in publications if self.is_diabetes_related(pub)]
            print(f"  Found {len(diabetes_pubs)} diabetes-related publications")
            
            # Store total diabetes publications count
            self.total_diabetes_pubs[faculty] = len(diabetes_pubs)
            
            # Find collaborations
            collaborations = self.find_collaborations(diabetes_pubs, faculty)
            
            # Store collaborations
            if collaborations:
                print(f"  Found {len(collaborations)} collaborative publications")
                self.collaborations[faculty] = collaborations
            else:
                print("  No collaborative publications found")
            
            # Print progress summary
            print(f"  Progress: {processed}/{total_faculty} faculty processed")
            print(f"  Time elapsed: {time.time() - start_time:.1f}s")
            print("-" * 80)
        
        # Export results
        self.export_to_csv()
        print("\nAnalysis complete!")
        print(f"Total time: {time.time() - start_time:.1f}s")
        print(f"Results exported to cdtr_collaborations.csv")

async def main():
    analyzer = CDTRCollaborationAnalyzer("CDTR_MemberBase_Cleaned.csv")
    await analyzer.analyze_collaborations()

if __name__ == "__main__":
    asyncio.run(main()) 