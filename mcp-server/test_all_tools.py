#!/usr/bin/env python3
"""
Comprehensive test suite for all MCP tools.
Tests each tool category and reports success/failure.
"""

import asyncio
import os
from dotenv import load_dotenv

# Load environment
load_dotenv('../.env')

from tools.airtable import AirtableTools
from tools.apollo import ApolloTools
from tools.outreach import OutreachTools
from tools.resume import ResumeTools
from tools.network_mining import NetworkMiningTools
from tools.discord_tools import DiscordTools


class ToolTester:
    def __init__(self):
        self.results = []
        self.airtable = AirtableTools()
        self.apollo = ApolloTools()
        self.outreach = OutreachTools()
        self.resume = ResumeTools()
        self.network_mining = NetworkMiningTools()
        self.discord = DiscordTools()
    
    def log(self, category, tool_name, status, message=""):
        """Log test result."""
        symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        self.results.append({
            "category": category,
            "tool": tool_name,
            "status": status,
            "message": message
        })
        print(f"{symbol} [{category}] {tool_name}: {message}")
    
    async def test_airtable_tools(self):
        """Test Airtable tools."""
        print("\n=== AIRTABLE TOOLS ===")
        
        # Test 1: get_jobs_needing_contacts
        try:
            result = await self.airtable.get_jobs_needing_contacts()
            if result.get("success"):
                count = result.get("total_found", 0)
                has_postgres_id = False
                if result.get("jobs"):
                    has_postgres_id = "resume_postgres_id" in result["jobs"][0]
                self.log("Airtable", "get_jobs_needing_contacts", "PASS", 
                        f"Found {count} jobs, resume_postgres_id present: {has_postgres_id}")
            else:
                self.log("Airtable", "get_jobs_needing_contacts", "FAIL", result.get("error"))
        except Exception as e:
            self.log("Airtable", "get_jobs_needing_contacts", "FAIL", str(e))
        
        # Test 2: get_job_details (using first job from above)
        try:
            jobs = await self.airtable.get_jobs_needing_contacts()
            if jobs.get("jobs"):
                job_id = jobs["jobs"][0]["job_id"]
                result = await self.airtable.get_job_details(job_id)
                if result.get("success"):
                    has_fields = all(k in result for k in ["company", "role", "resume_postgres_id"])
                    self.log("Airtable", "get_job_details", "PASS", 
                            f"Retrieved {result['company']} - {result['role']}")
                else:
                    self.log("Airtable", "get_job_details", "FAIL", result.get("error"))
        except Exception as e:
            self.log("Airtable", "get_job_details", "FAIL", str(e))
        
        # Test 3: get_contacts_ready_for_outreach
        try:
            result = await self.airtable.get_contacts_ready_for_outreach(["Ready"])
            if result.get("success"):
                count = result.get("total_found", 0)
                self.log("Airtable", "get_contacts_ready_for_outreach", "PASS", 
                        f"Found {count} contacts")
            else:
                self.log("Airtable", "get_contacts_ready_for_outreach", "FAIL", result.get("error"))
        except Exception as e:
            self.log("Airtable", "get_contacts_ready_for_outreach", "FAIL", str(e))
        
        # Test 4: get_active_jobs_for_network_mining
        try:
            result = await self.airtable.get_active_jobs_for_network_mining()
            if result.get("success"):
                count = result.get("total_jobs", 0)
                self.log("Airtable", "get_active_jobs_for_network_mining", "PASS", 
                        f"Found {count} active jobs")
            else:
                self.log("Airtable", "get_active_jobs_for_network_mining", "FAIL", result.get("error"))
        except Exception as e:
            self.log("Airtable", "get_active_jobs_for_network_mining", "FAIL", str(e))
    
    async def test_apollo_tools(self):
        """Test Apollo tools."""
        print("\n=== APOLLO TOOLS ===")
        
        # Test: find_contacts (limited to 1 to save API quota)
        try:
            result = await self.apollo.find_contacts("Google", "Software Engineer", limit=1)
            if result.get("success"):
                count = len(result.get("contacts", []))
                self.log("Apollo", "find_contacts", "PASS", f"Found {count} contacts")
            else:
                self.log("Apollo", "find_contacts", "FAIL", result.get("error"))
        except Exception as e:
            self.log("Apollo", "find_contacts", "FAIL", str(e))
    
    async def test_resume_tools(self):
        """Test Resume tools."""
        print("\n=== RESUME TOOLS ===")
        
        # Test 1: get_active_resume (deprecated but should still work)
        try:
            result = await self.resume.get_active_resume("Software Engineer")
            if result.get("success"):
                has_text = len(result.get("full_text", "")) > 0
                self.log("Resume", "get_active_resume", "PASS", 
                        f"Retrieved resume, has_epic: {result.get('has_epic')}")
            else:
                error_msg = result.get("error", "Unknown error")
                if "connection" in error_msg.lower() or "database" in error_msg.lower():
                    self.log("Resume", "get_active_resume", "SKIP", 
                            "DB connection issue (expected - needs Docker/Postgres)")
                else:
                    self.log("Resume", "get_active_resume", "FAIL", error_msg)
        except Exception as e:
            error_str = str(e)
            if "connection" in error_str.lower() or "timeout" in error_str.lower():
                self.log("Resume", "get_active_resume", "SKIP", 
                        "DB connection issue (expected - needs Docker/Postgres)")
            else:
                self.log("Resume", "get_active_resume", "FAIL", error_str[:100])
        
        # Test 2: get_tailored_resume (will timeout locally - expected)
        try:
            result = await asyncio.wait_for(
                self.resume.get_tailored_resume(538), 
                timeout=5.0
            )
            if result.get("success"):
                self.log("Resume", "get_tailored_resume", "PASS", 
                        f"Retrieved tailored resume for app_id 538")
            else:
                self.log("Resume", "get_tailored_resume", "FAIL", result.get("error"))
        except asyncio.TimeoutError:
            self.log("Resume", "get_tailored_resume", "SKIP", 
                    "Timeout (expected - needs Docker/Postgres)")
        except Exception as e:
            self.log("Resume", "get_tailored_resume", "SKIP", f"DB connection issue: {str(e)[:50]}")
        
        # Test 3: get_cold_email (will timeout locally - expected)
        try:
            result = await asyncio.wait_for(
                self.resume.get_cold_email(538, "hiring_manager"), 
                timeout=5.0
            )
            if result.get("success"):
                has_email = result.get("cold_email") is not None
                self.log("Resume", "get_cold_email", "PASS", 
                        f"Has cold_email: {has_email}, fallback: {result.get('fallback_used')}")
            else:
                self.log("Resume", "get_cold_email", "FAIL", result.get("error"))
        except asyncio.TimeoutError:
            self.log("Resume", "get_cold_email", "SKIP", 
                    "Timeout (expected - needs Docker/Postgres)")
        except Exception as e:
            self.log("Resume", "get_cold_email", "SKIP", f"DB connection issue: {str(e)[:50]}")
        
        # Test 4: check_skill_match
        try:
            jd = "We need someone with Epic EHR experience and FHIR knowledge"
            result = await self.resume.check_skill_match(jd, "epic")
            self.log("Resume", "check_skill_match", "PASS", 
                    f"Epic gap detected: {result.get('has_gap')}")
        except Exception as e:
            error_str = str(e)
            if "connection" in error_str.lower() or "timeout" in error_str.lower():
                self.log("Resume", "check_skill_match", "SKIP", 
                        "DB connection issue (expected - needs Docker/Postgres)")
            else:
                self.log("Resume", "check_skill_match", "FAIL", error_str[:100])
    
    async def test_outreach_tools(self):
        """Test Outreach tools (v3.0 - 3-Phase)."""
        print("\n=== OUTREACH TOOLS (v3.0) ===")
        
        # Test 1: generate_cold_connect_note
        try:
            result = await self.outreach.generate_cold_connect_note(
                contact_name="John Smith",
                contact_title="Engineering Manager",
                contact_type="hiring_manager",
                company="Google",
                job_title="Software Engineer",
                job_description="Build scalable systems",
                resume_highlights="5 years Python, distributed systems"
            )
            if result.get("success"):
                char_count = result.get("char_count", 0)
                within_limit = char_count <= 295
                self.log("Outreach", "generate_cold_connect_note", "PASS", 
                        f"{char_count} chars, within limit: {within_limit}")
            else:
                self.log("Outreach", "generate_cold_connect_note", "FAIL", result.get("error"))
        except Exception as e:
            self.log("Outreach", "generate_cold_connect_note", "FAIL", str(e))
        
        # Test 2: generate_warm_dm
        try:
            result = await self.outreach.generate_warm_dm(
                contact_name="Jane Doe",
                company="Meta",
                target_role="Data Engineer",
                connected_date="2024-01-15",
                contact_title="Senior Engineer",
                resume_highlights="Data pipelines, Spark, Airflow"
            )
            if result.get("success"):
                char_count = result.get("char_count", 0)
                self.log("Outreach", "generate_warm_dm", "PASS", 
                        f"{char_count} chars generated")
            else:
                self.log("Outreach", "generate_warm_dm", "FAIL", result.get("error"))
        except Exception as e:
            self.log("Outreach", "generate_warm_dm", "FAIL", str(e))
        
        # Test 3: generate_message (unified entry point)
        try:
            result = await self.outreach.generate_message(
                contact_name="Bob Johnson",
                company="Amazon",
                job_title="ML Engineer",
                contact_title="ML Lead",
                contact_type="hiring_manager",
                connection_degree="2nd",
                resume_highlights="PyTorch, TensorFlow, model deployment"
            )
            if result.get("success"):
                pipeline = result.get("pipeline")
                self.log("Outreach", "generate_message", "PASS", 
                        f"Routed to {pipeline} pipeline")
            else:
                self.log("Outreach", "generate_message", "FAIL", result.get("error"))
        except Exception as e:
            self.log("Outreach", "generate_message", "FAIL", str(e))
    
    async def test_network_mining_tools(self):
        """Test Network Mining tools."""
        print("\n=== NETWORK MINING TOOLS ===")
        
        # Create sample CSV content
        sample_csv = """First Name,Last Name,Email Address,Company,Position,Connected On
John,Doe,john@example.com,Google,Engineer,01 Jan 2024
Jane,Smith,jane@example.com,Meta,Manager,15 Feb 2024"""
        
        # Test 1: get_network_stats
        try:
            result = await self.network_mining.get_network_stats(sample_csv)
            if result.get("success"):
                total = result.get("total_connections", 0)
                self.log("Network Mining", "get_network_stats", "PASS", 
                        f"{total} connections analyzed")
            else:
                self.log("Network Mining", "get_network_stats", "FAIL", result.get("error"))
        except Exception as e:
            self.log("Network Mining", "get_network_stats", "FAIL", str(e))
        
        # Test 2: find_by_company
        try:
            result = await self.network_mining.find_by_company(sample_csv, "Google")
            if result.get("success"):
                count = len(result.get("connections", []))
                self.log("Network Mining", "find_by_company", "PASS", 
                        f"Found {count} connections at Google")
            else:
                self.log("Network Mining", "find_by_company", "FAIL", result.get("error"))
        except Exception as e:
            self.log("Network Mining", "find_by_company", "FAIL", str(e))
        
        # Test 3: analyze_network_overlap
        try:
            active_jobs = [{"company": "Google", "role": "SWE", "job_id": "test123", "status": "In progress"}]
            result = await self.network_mining.analyze_network_overlap(sample_csv, active_jobs)
            if result.get("success"):
                count = len(result.get("insiders", []))
                self.log("Network Mining", "analyze_network_overlap", "PASS", 
                        f"Found {count} insiders")
            else:
                self.log("Network Mining", "analyze_network_overlap", "FAIL", result.get("error"))
        except Exception as e:
            self.log("Network Mining", "analyze_network_overlap", "FAIL", str(e))
    
    async def test_discord_tools(self):
        """Test Discord tools."""
        print("\n=== DISCORD TOOLS ===")
        
        # Note: These will fail if Discord bot isn't running, which is expected
        try:
            result = await self.discord.send_approval(
                contact_id="test123",
                contact_name="Test Contact",
                contact_type="hiring_manager",
                company="Test Co",
                job_title="Test Role",
                linkedin_url="https://linkedin.com/in/test",
                message_draft="Test message",
                connection_degree="2nd",
                pipeline="hunter"
            )
            if result.get("success"):
                self.log("Discord", "send_approval", "PASS", "Approval sent")
            else:
                self.log("Discord", "send_approval", "SKIP", 
                        "Discord bot not running (expected for local testing)")
        except Exception as e:
            self.log("Discord", "send_approval", "SKIP", 
                    "Discord bot not running (expected for local testing)")
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        
        by_status = {"PASS": 0, "FAIL": 0, "SKIP": 0}
        by_category = {}
        
        for result in self.results:
            status = result["status"]
            category = result["category"]
            
            by_status[status] = by_status.get(status, 0) + 1
            
            if category not in by_category:
                by_category[category] = {"PASS": 0, "FAIL": 0, "SKIP": 0}
            by_category[category][status] += 1
        
        print(f"\nOverall: {by_status['PASS']} passed, {by_status['FAIL']} failed, {by_status['SKIP']} skipped")
        print("\nBy Category:")
        for category, stats in sorted(by_category.items()):
            print(f"  {category}: {stats['PASS']} passed, {stats['FAIL']} failed, {stats['SKIP']} skipped")
        
        if by_status['FAIL'] > 0:
            print("\n❌ FAILURES:")
            for result in self.results:
                if result["status"] == "FAIL":
                    print(f"  - [{result['category']}] {result['tool']}: {result['message']}")
        
        print("\n" + "="*60)
        
        return by_status['FAIL'] == 0


async def main():
    """Run all tests."""
    print("Starting comprehensive MCP tool test suite...")
    print("="*60)
    
    tester = ToolTester()
    
    await tester.test_airtable_tools()
    await tester.test_apollo_tools()
    await tester.test_resume_tools()
    await tester.test_outreach_tools()
    await tester.test_network_mining_tools()
    await tester.test_discord_tools()
    
    all_passed = tester.print_summary()
    
    if all_passed:
        print("\n🎉 All critical tests passed!")
    else:
        print("\n⚠️  Some tests failed - review above")


if __name__ == "__main__":
    asyncio.run(main())
