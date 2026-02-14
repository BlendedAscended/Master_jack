import os
import sys
import asyncio
import httpx
import json
from pathlib import Path
from dotenv import load_dotenv

# ANSI Colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

def log_success(msg):
    print(f"{GREEN}[✓] {msg}{RESET}")

def log_error(msg):
    print(f"{RED}[✗] {msg}{RESET}")

def log_warn(msg):
    print(f"{YELLOW}[!] {msg}{RESET}")

def log_info(msg):
    print(f"[-] {msg}")

async def check_airtable_schema(api_key, base_id):
    log_info("Checking Airtable Schema...")
    
    base_url = f"https://api.airtable.com/v0/{base_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Define required fields per table
    required_schema = {
        "Applications": [
            "Status", "Job Link", "Company", "Job Position", 
            "Full Description", "Contacts_Found"
        ],
        "Contacts": [
            "Name", "Title", "LinkedIn_URL", "Priority", 
            "Job_Application", "Outreach_Status", "Contact_Type"
        ]
    }
    
    async with httpx.AsyncClient(timeout=10) as client:
        for table, fields in required_schema.items():
            url = f"{base_url}/{table}"
            try:
                response = await client.get(url, headers=headers, params={"maxRecords": 1})
                if response.status_code == 200:
                    records = response.json().get("records", [])
                    if records:
                        existing_fields = records[0].get("fields", {}).keys()
                        missing = [f for f in fields if f not in existing_fields]
                        
                        if missing:
                            log_error(f"Table '{table}' is missing fields: {', '.join(missing)}")
                        else:
                            log_success(f"Table '{table}' schema looks correct.")
                    else:
                        log_warn(f"Table '{table}' is empty. Cannot verify schema fields.")
                elif response.status_code == 404:
                     log_error(f"Table '{table}' not found in Base.")
                else:
                    log_error(f"Error accessing '{table}': {response.status_code} - {response.text}")
            except Exception as e:
                log_error(f"Exception checking '{table}': {str(e)}")

async def main():
    print("=== Titan-Brain Diagnostic Tool ===\n")
    
    # 1. Check .env
    env_path = Path('.env')
    if env_path.exists():
        log_success("Found .env file")
        load_dotenv()
    else:
        log_warn(".env file not found in current directory. Checking environment variables directy.")
    
    # 2. Check Variables
    required_vars = [
        "AIRTABLE_API_KEY", "AIRTABLE_BASE_ID", 
        "DEEPSEEK_API_KEY", "APIFY_API_TOKEN"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        log_error(f"Missing environment variables: {', '.join(missing_vars)}")
        # Only proceed with Airtable check if keys are present
        if "AIRTABLE_API_KEY" in missing_vars or "AIRTABLE_BASE_ID" in missing_vars:
            print("\nCannot proceed with Airtable check due to missing keys.")
            return
    else:
        log_success("All required environment variables are present.")

    # 3. Check Airtable Schema & Connectivity
    api_key = os.getenv("AIRTABLE_API_KEY")
    base_id = os.getenv("AIRTABLE_BASE_ID")
    
    if api_key and base_id:
        await check_airtable_schema(api_key, base_id)

    print("\nDiagnostic complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAborted.")
