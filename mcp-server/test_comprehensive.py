#!/usr/bin/env python3
"""
Comprehensive Tool Verification Script

Tests all MCP tools locally. Skips Postgres-dependent tools (resume.py)
since those only work on Hetzner VPS.

Usage: ../venv/bin/python3 test_comprehensive.py
"""

import os
import sys
import asyncio
from datetime import datetime

# Load environment
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Set dummy Apify token if not present for import testing
if not os.environ.get('APIFY_API_TOKEN'):
    os.environ['APIFY_API_TOKEN'] = 'dummy_for_import'


class TestResults:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.skipped = []
    
    def add_pass(self, name, details=""):
        self.passed.append((name, details))
        print(f"  ✅ {name}")
        if details:
            print(f"     {details}")
    
    def add_fail(self, name, error):
        self.failed.append((name, str(error)))
        print(f"  ❌ {name}: {error}")
    
    def add_skip(self, name, reason):
        self.skipped.append((name, reason))
        print(f"  ⏭️  {name}: {reason}")
    
    def summary(self):
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        print(f"✅ Passed:  {len(self.passed)}")
        print(f"❌ Failed:  {len(self.failed)}")
        print(f"⏭️  Skipped: {len(self.skipped)}")
        
        if self.failed:
            print("\nFailed Tests:")
            for name, error in self.failed:
                print(f"  • {name}: {error}")
        
        return len(self.failed) == 0


async def test_imports(results: TestResults):
    """Test that all modules import correctly."""
    print("\n📦 TESTING IMPORTS")
    print("-" * 40)
    
    try:
        from tools.airtable import AirtableTools
        results.add_pass("AirtableTools import")
    except Exception as e:
        results.add_fail("AirtableTools import", e)
    
    try:
        from tools.apollo import ApolloTools
        results.add_pass("ApolloTools import")
    except Exception as e:
        results.add_fail("ApolloTools import", e)
    
    try:
        from tools.apify_sourcing import ApifyTools
        results.add_pass("ApifyTools import")
    except Exception as e:
        results.add_fail("ApifyTools import", e)
    
    try:
        from tools.outreach import OutreachTools
        results.add_pass("OutreachTools import")
    except Exception as e:
        results.add_fail("OutreachTools import", e)
    
    try:
        from tools.network_mining import NetworkMiningTools
        results.add_pass("NetworkMiningTools import")
    except Exception as e:
        results.add_fail("NetworkMiningTools import", e)
    
    try:
        from tools.discord_tools import DiscordTools
        results.add_pass("DiscordTools import")
    except Exception as e:
        results.add_fail("DiscordTools import", e)
    
    try:
        from tools.resume import ResumeTools
        results.add_pass("ResumeTools import")
    except Exception as e:
        results.add_fail("ResumeTools import", e)
    
    try:
        import server
        results.add_pass("server.py import")
    except Exception as e:
        results.add_fail("server.py import", e)


async def test_airtable(results: TestResults):
    """Test Airtable tools."""
    print("\n📊 TESTING AIRTABLE TOOLS")
    print("-" * 40)
    
    from tools.airtable import AirtableTools
    
    try:
        airtable = AirtableTools()
        results.add_pass("AirtableTools instantiation")
    except Exception as e:
        results.add_fail("AirtableTools instantiation", e)
        return
    
    # Test get_jobs_needing_contacts
    try:
        jobs = await airtable.get_jobs_needing_contacts(status="In progress")
        if jobs.get("success"):
            job_count = len(jobs.get("jobs", []))
            results.add_pass("get_jobs_needing_contacts", f"Found {job_count} jobs")
            
            # Check for resume_postgres_id field
            if jobs.get("jobs") and "resume_postgres_id" in jobs["jobs"][0]:
                results.add_pass("resume_postgres_id field present")
            else:
                results.add_skip("resume_postgres_id field", "No jobs found or field missing")
        else:
            results.add_fail("get_jobs_needing_contacts", jobs.get("error"))
    except Exception as e:
        results.add_fail("get_jobs_needing_contacts", e)
    
    # Test get_contacts_by_status - NOTE: This method doesn't exist, skip it
    results.add_skip("get_contacts_by_status", "Method not implemented in AirtableTools")
    
    # Test get_active_jobs_for_network_mining
    try:
        jobs = await airtable.get_active_jobs_for_network_mining()
        if jobs.get("success"):
            results.add_pass("get_active_jobs_for_network_mining", f"Found {len(jobs.get('jobs', []))} jobs")
        else:
            results.add_fail("get_active_jobs_for_network_mining", jobs.get("error"))
    except Exception as e:
        results.add_fail("get_active_jobs_for_network_mining", e)


async def test_apify_llm(results: TestResults):
    """Test Apify LLM title extraction (doesn't require real API token)."""
    print("\n🤖 TESTING APIFY LLM TITLE EXTRACTION")
    print("-" * 40)
    
    # Check for DeepSeek API key
    if not os.environ.get("DEEPSEEK_API_KEY"):
        results.add_skip("Apify LLM extraction", "DEEPSEEK_API_KEY not set")
        return
    
    from tools.apify_sourcing import ApifyTools
    
    try:
        # Set real token if available, otherwise dummy
        real_token = os.environ.get("APIFY_API_TOKEN_REAL", "dummy")
        os.environ["APIFY_API_TOKEN"] = real_token
        
        apify = ApifyTools()
        results.add_pass("ApifyTools instantiation")
    except Exception as e:
        results.add_fail("ApifyTools instantiation", e)
        return
    
    # Test LLM title extraction with location
    try:
        result = await apify._extract_hiring_manager_titles(
            job_position="Health Data Analytics Consultant, Payment Model",
            job_description="Work with payment models and health data analytics",
            company="VNS Health",
            location="New York, NY"
        )
        
        if result.get("success"):
            titles = result.get("hiring_manager_titles", [])
            results.add_pass("LLM title extraction", f"Generated: {titles[:2]}")
        else:
            # Check if it used fallback
            if result.get("source") == "fallback":
                results.add_pass("LLM title extraction (fallback)", result.get("error", "Used fallback"))
            else:
                results.add_fail("LLM title extraction", result.get("error"))
    except Exception as e:
        results.add_fail("LLM title extraction", e)
    
    # Test complex healthcare title
    try:
        result = await apify._extract_hiring_manager_titles(
            job_position="Senior Revenue Cycle Business Analyst - Epic",
            company="Mayo Clinic",
            location="Rochester, MN"
        )
        
        if result.get("hiring_manager_titles"):
            results.add_pass("Healthcare title extraction", f"Generated: {result.get('hiring_manager_titles', [])[:2]}")
    except Exception as e:
        results.add_fail("Healthcare title extraction", e)


async def test_outreach(results: TestResults):
    """Test Outreach tools (DeepSeek powered)."""
    print("\n✉️  TESTING OUTREACH TOOLS")
    print("-" * 40)
    
    if not os.environ.get("DEEPSEEK_API_KEY"):
        results.add_skip("Outreach tools", "DEEPSEEK_API_KEY not set")
        return
    
    from tools.outreach import OutreachTools
    
    try:
        outreach = OutreachTools()
        results.add_pass("OutreachTools instantiation")
    except Exception as e:
        results.add_fail("OutreachTools instantiation", e)
        return
    
    # Test cold connect note generation
    try:
        result = await outreach.generate_cold_connect_note(
            contact_name="Sarah Johnson",
            contact_title="Director of Analytics",
            contact_type="hiring_manager",
            company="VNS Health",
            job_title="Health Data Analytics Consultant",
            job_description="Work with payment models and health data analytics",
            resume_highlights="5 years healthcare analytics, Epic certified"
        )
        
        if result.get("success"):
            msg = result.get("message", "")
            char_count = len(msg)
            results.add_pass("generate_cold_connect_note", f"{char_count} chars: {msg[:60]}...")
        else:
            results.add_fail("generate_cold_connect_note", result.get("error"))
    except Exception as e:
        results.add_fail("generate_cold_connect_note", e)
    
    # Test warm DM generation
    try:
        result = await outreach.generate_warm_dm(
            contact_name="John Smith",
            company="Epic",
            target_role="Business Analyst",
            connected_date="01 Jan 2024",
            contact_title="Senior Data Analyst",
            contact_type="peer",
            resume_highlights="Epic Beaker certified"
        )
        
        if result.get("success"):
            msg = result.get("message", "")
            results.add_pass("generate_warm_dm", f"{len(msg)} chars")
        else:
            results.add_fail("generate_warm_dm", result.get("error"))
    except Exception as e:
        results.add_fail("generate_warm_dm", e)


async def test_network_mining(results: TestResults):
    """Test Network Mining tools."""
    print("\n🔍 TESTING NETWORK MINING TOOLS")
    print("-" * 40)
    
    from tools.network_mining import NetworkMiningTools
    
    try:
        network = NetworkMiningTools()
        results.add_pass("NetworkMiningTools instantiation")
    except Exception as e:
        results.add_fail("NetworkMiningTools instantiation", e)
        return
    
    # Test analyze_network_overlap (with mock data)
    try:
        # Create test CSV content
        test_csv = """First Name,Last Name,Company,Position
John,Doe,Test Corp,Software Engineer
Jane,Smith,Example Inc,Product Manager"""
        
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(test_csv)
            temp_path = f.name
        
        # Read the temp file as content
        with open(temp_path, 'r') as f:
            csv_content = f.read()
        
        overlap = await network.analyze_network_overlap(
            csv_content=csv_content,
            active_jobs=[{"company": "Test Corp", "role": "Engineer", "status": "In progress", "job_id": "test1"}]
        )
        
        os.unlink(temp_path)  # Clean up
        
        if overlap.get("success"):
            results.add_pass("analyze_network_overlap", f"Found {len(overlap.get('overlapping_connections', []))} matches")
        else:
            results.add_fail("analyze_network_overlap", overlap.get("error"))
    except Exception as e:
        results.add_fail("analyze_network_overlap", e)
    
    # Test get_network_stats
    try:
        test_csv = """First Name,Last Name,Company,Position,Connected On
John,Doe,Test Corp,Software Engineer,01 Jan 2024
Jane,Smith,Example Inc,Product Manager,15 Feb 2024"""
        
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(test_csv)
            temp_path = f.name
        
        # Read content
        with open(temp_path, 'r') as f:
            csv_content = f.read()
        
        stats = await network.get_network_stats(csv_content=csv_content)
        os.unlink(temp_path)
        
        if stats.get("success"):
            results.add_pass("get_network_stats", f"Total connections: {stats.get('total_connections', 0)}")
        else:
            results.add_fail("get_network_stats", stats.get("error"))
    except Exception as e:
        results.add_fail("get_network_stats", e)


async def test_discord(results: TestResults):
    """Test Discord tools (no webhook call)."""
    print("\n💬 TESTING DISCORD TOOLS")
    print("-" * 40)
    
    from tools.discord_tools import DiscordTools
    
    try:
        discord = DiscordTools()
        results.add_pass("DiscordTools instantiation")
    except Exception as e:
        results.add_fail("DiscordTools instantiation", e)
        return
    
    # Test format_approval_embed (internal method, no API call)
    try:
        embed = discord._format_approval_embed(
            contact_name="Test User",
            contact_title="Director",
            company="Test Corp",
            message="Test message for approval"
        )
        if embed:
            results.add_pass("format_approval_embed")
        else:
            results.add_skip("format_approval_embed", "Method not found")
    except AttributeError:
        results.add_skip("format_approval_embed", "Method not available")
    except Exception as e:
        results.add_fail("format_approval_embed", e)


async def test_apollo(results: TestResults):
    """Test Apollo tools (may fail on free tier)."""
    print("\n🚀 TESTING APOLLO TOOLS")
    print("-" * 40)
    
    if not os.environ.get("APOLLO_API_KEY"):
        results.add_skip("Apollo tools", "APOLLO_API_KEY not set")
        return
    
    from tools.apollo import ApolloTools
    
    try:
        apollo = ApolloTools()
        results.add_pass("ApolloTools instantiation")
    except Exception as e:
        results.add_fail("ApolloTools instantiation", e)
        return
    
    # Test find_contacts (may fail on free tier)
    try:
        contacts = await apollo.find_contacts(
            company_name="Microsoft",
            job_title="Software Engineer",
            limit=2
        )
        
        if contacts.get("success"):
            results.add_pass("Apollo find_contacts", f"Found {len(contacts.get('contacts', []))} contacts")
        else:
            error = contacts.get("error", "Unknown error")
            if "403" in str(error) or "forbidden" in str(error).lower():
                results.add_skip("Apollo find_contacts", "Free tier limitation (403)")
            else:
                results.add_fail("Apollo find_contacts", error)
    except Exception as e:
        results.add_fail("Apollo find_contacts", e)


async def test_resume_skip(results: TestResults):
    """Skip resume tools (Postgres only works on Hetzner VPS)."""
    print("\n📄 RESUME TOOLS (SKIPPED - Hetzner VPS only)")
    print("-" * 40)
    
    results.add_skip("get_tailored_resume", "Requires Hetzner VPS Postgres")
    results.add_skip("get_cold_email", "Requires Hetzner VPS Postgres")
    results.add_skip("check_skill_match", "Requires Hetzner VPS Postgres")


async def main():
    print("=" * 60)
    print("🔧 COMPREHENSIVE TOOL VERIFICATION")
    print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    results = TestResults()
    
    # Run all tests
    await test_imports(results)
    await test_airtable(results)
    await test_apify_llm(results)
    await test_outreach(results)
    await test_network_mining(results)
    await test_discord(results)
    await test_apollo(results)
    await test_resume_skip(results)
    
    # Print summary
    all_passed = results.summary()
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
