#!/usr/bin/env python3
"""Test script for Titan MCP Server"""

import asyncio
import os
import sys

# Add the current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from tools.outreach import OutreachTools


async def test_outreach():
    print("=" * 60)
    print("Testing Titan MCP Server - Outreach Tools")
    print("=" * 60)
    print()
    
    outreach = OutreachTools()
    print(f"✓ OutreachTools initialized (base_url: {outreach.client.base_url})")
    print()
    
    print("Generating cold connect note via DeepSeek API...")
    result = await outreach.generate_cold_connect_note(
        contact_name="Sarah Johnson",
        company="Epic Systems",
        job_title="Senior Data Analyst",
        job_description="Looking for Senior Data Analyst with Epic certification to join our team.",
        resume_highlights="5 years healthcare analytics, SQL expert, Python, Tableau certified",
    )
    
    print()
    print("Result:")
    print(f"  Success: {result['success']}")
    print(f"  Pipeline: {result['pipeline']}")
    print(f"  Char count: {result['char_count']} / {result['max_allowed']}")
    print(f"  Epic gap: {result['has_epic_gap']}")
    print()
    print("Generated message:")
    print("-" * 40)
    print(result['message'])
    print("-" * 40)


if __name__ == "__main__":
    asyncio.run(test_outreach())
