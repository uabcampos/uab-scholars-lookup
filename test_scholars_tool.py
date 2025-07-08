import asyncio
from uab_scholars_tool import Tools
import json

async def test_cherrington():
    """Test the updated UAB Scholars Tool with Andrea Cherrington's profile."""
    tool = Tools()
    
    # Test 1: General faculty inquiry
    print("\nTest 1: General faculty inquiry")
    print("--------------------------------")
    result = await tool.search_scholars("Andrea Cherrington")
    data = json.loads(result)
    
    if data[0]["status"] == "found":
        profile = data[0]["profile"]
        print(f"\nProfile Information:")
        print(f"Name: {profile['name']}")
        print(f"Department: {profile['department']}")
        print(f"Position: {profile['position']}")
        print(f"Profile URL: {profile['url']}")
        print(f"\nTeaching Interests:")
        print(profile.get('teaching_interests', 'No teaching interests listed'))
        
        print(f"\nTeaching Activities ({data[0]['teaching_activities']['total']}):")
        for activity in data[0]['teaching_activities']['list'][:3]:
            print(f"\nType: {activity['type']}")
            print(f"Title: {activity['title']}")
            print(f"Period: {activity['startYear']}-{activity['endYear']}")
    else:
        print("Error:", data.get("message", "Unknown error"))
    
    # Test 2: Specific information request (teaching activities only)
    print("\nTest 2: Specific information request (teaching activities)")
    print("--------------------------------------------------------")
    if data[0]["status"] == "found":
        profile = data[0]["profile"]
        print(f"\nTeaching Activities for {profile['name']}:")
        print(f"Total Activities: {data[0]['teaching_activities']['total']}")
        for activity in data[0]['teaching_activities']['list'][:3]:
            print(f"\nType: {activity['type']}")
            print(f"Title: {activity['title']}")
            print(f"Period: {activity['startYear']}-{activity['endYear']}")
        print(f"\nFor more information, visit their UAB Scholars profile: {profile['url']}")
    else:
        print("Error:", data.get("message", "Unknown error"))

if __name__ == "__main__":
    asyncio.run(test_cherrington()) 