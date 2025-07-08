#!/usr/bin/env python3

from uab_scholars_tool import Tools
import json

def test_department_count(department: str, tool: Tools):
    """Test counting faculty in a department."""
    print(f"\nTesting department: {department}")
    
    # Test count only
    count = tool.count_faculty_in_department(department)
    print(f"Count: {count}")
    
    # Test getting list
    faculty_list = tool.count_faculty_in_department(department, return_list=True)
    print(f"Found {len(faculty_list)} faculty members")
    
    # Print first 3 faculty members if any found
    if faculty_list:
        print("\nFirst 3 faculty members:")
        for i, faculty in enumerate(faculty_list[:3], 1):
            print(f"\n{i}. {faculty['name']}")
            print(f"   Position: {faculty['position']}")
            print(f"   Department: {faculty['department']}")
            print(f"   Email: {faculty['email']}")
            print(f"   URL: {faculty['url']}")

def main():
    tool = Tools()
    
    # Test different department formats
    departments = [
        "Med - Preventive Medicine",
        "Preventive Medicine",
        "Medicine - Preventive Medicine",
        "School of Medicine - Preventive Medicine",
        "Department of Preventive Medicine"
    ]
    
    for dept in departments:
        test_department_count(dept, tool)

if __name__ == "__main__":
    main() 