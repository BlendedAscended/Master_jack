import os
import asyncio
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'mcp-server'))
from tools.airtable import AirtableTools
from dotenv import load_dotenv

load_dotenv()

async def test_fetch():
    airtable = AirtableTools()
    job_id = "rec0AH6wTYAWOBEVx" # The ID from the screenshot
    
    print(f"Attempting to fetch job {job_id}...")
    result = await airtable.get_job_details(job_id)
    print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(test_fetch())
