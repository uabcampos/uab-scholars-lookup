import asyncio
from uab_scholars_tool import Tools

async def test_tool():
    # Initialize the tool
    tool = Tools()
    
    # Test search_scholars
    print("\nTesting search_scholars:")
    result = await tool.search_scholars("Andrea Cherrington")
    print(result)
    
    # Test get_scholar_by_id
    print("\nTesting get_scholar_by_id:")
    result = await tool.get_scholar_by_id("450")
    print(result)
    
    # Test search_by_department
    print("\nTesting search_by_department:")
    result = await tool.search_by_department("Preventive Medicine")
    print(result)
    
    # Test get_faculty_list
    print("\nTesting get_faculty_list:")
    result = await tool.get_faculty_list("Preventive Medicine")
    print(result)

if __name__ == "__main__":
    asyncio.run(test_tool()) 