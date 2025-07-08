import asyncio
import json
from uab_scholars_tool import UABScholarsTool

async def search_cancer_experts():
    # Initialize the tool
    tool = UABScholarsTool()
    
    # Define cancer-related keywords
    cancer_keywords = [
        "cancer",
        "oncology",
        "tumor",
        "carcinoma",
        "malignant",
        "chemotherapy",
        "radiation",
        "metastasis",
        "cancer research",
        "cancer treatment"
    ]
    
    # Search for cancer research experts
    result = await tool.search_by_expertise(
        keywords=cancer_keywords,
        start_id=1,
        end_id=1000,  # Search first 1000 scholars
        max_results=10  # Get top 10 matches
    )
    
    # Parse the JSON response
    data = json.loads(result)
    
    # Print raw response for debugging
    print("\nRaw Response:")
    print(json.dumps(data, indent=2))
    
    # Check if the response has the expected type
    if data.get("type") != "expertise_search_results":
        print(f"\nUnexpected response type: {data.get('type')}")
        return
    
    # Print the human-readable message
    print(f"\n{data['message']}")
    
    # Print detailed information about each match
    for match in data.get("results", []):
        print("\n" + "="*80)
        print(f"Name: {match['name']}")
        print(f"Department: {match['department']}")
        print(f"Position: {match['position']}")
        print(f"Profile URL: {match['profile_url']}")
        print(f"Match Score: {match['match_score']}")
        print("\nTeaching Interests:")
        print(match['teaching_interests'])
        
        print("\nRecent Publications:")
        for pub in match['recent_publications']:
            print(f"- {pub}")
            
        print("\nRecent Grants:")
        for grant in match['recent_grants']:
            print(f"- {grant}")

if __name__ == "__main__":
    asyncio.run(search_cancer_experts()) 