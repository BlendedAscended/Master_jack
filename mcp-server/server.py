# mcp-server/server.py
"""
Titan MCP Server (v3.0) — 3-Phase Outreach Pipeline

Main entry point for the Titan Outreach MCP Server.
Uses FastMCP for tool registration.

v3.0 Changes:
- get_outreach_context: Resolves full linking chain in one call
- get_tailored_resume: Fetches JD-tailored resume by application_id
- get_cold_email: Routes to cold_email_manager or cold_email_recruiter
- Updated outreach tools with 3-Phase params (contact_title, contact_type, cold_email_template)
- Removed conversation_hooks (replaced by contact_title/type for Hook phase)
"""

import os
from typing import Optional
from mcp.server.fastmcp import FastMCP

# Load environment if not already loaded
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Import tool classes
from tools.airtable import AirtableTools
from tools.apollo import ApolloTools
from tools.apify_sourcing import ApifyTools
from tools.outreach import OutreachTools
from tools.resume import ResumeTools
from tools.network_mining import NetworkMiningTools
from tools.discord_tools import DiscordTools
from tools.second_brain import SecondBrainTools
from tools.chat_ingest import ChatIngestTools
from tools.content import ContentTools

# Initialize FastMCP server
mcp = FastMCP("titan-outreach")

# Initialize tool instances
airtable = AirtableTools()
apollo = ApolloTools()
apify = ApifyTools()
outreach = OutreachTools()
resume = ResumeTools()
network_mining = NetworkMiningTools()
discord = DiscordTools()
second_brain = SecondBrainTools()
chat_ingest = ChatIngestTools()
content_tools = ContentTools()


# ==================== AIRTABLE TOOLS ====================

@mcp.tool()
async def get_jobs_needing_contacts(status: str = "In progress") -> dict:
    """
    Get job applications that need contact discovery.
    
    CRITICAL: Only "In progress" jobs are eligible for outreach (v2.0).
    "Todo" jobs are NOT processed.
    
    Args:
        status: Job status to filter by (default: "In progress")
    
    Returns:
        List of jobs with company, role, job_description, resume_postgres_id
    """
    return await airtable.get_jobs_needing_contacts(status)


@mcp.tool()
async def get_job_details(job_id: str) -> dict:
    """
    Get full details of a specific job application.
    Includes Full Description, Skill Audit, resume_postgres_id.
    """
    return await airtable.get_job_details(job_id)


@mcp.tool()
async def get_contacts_ready_for_outreach() -> dict:
    """
    Get contacts that are ready for message drafting.
    Returns contacts with status "Ready".
    """
    return await airtable.get_contacts_ready_for_outreach(["Ready"])


@mcp.tool()
async def save_contacts_to_airtable(job_id: str, contacts: list[dict]) -> dict:
    """
    Save discovered contacts to Airtable, linked to the job application.
    
    Each contact should have:
    - name, title, linkedin_url, email (optional)
    - contact_type, contact_source, connection_degree, priority
    """
    result = await airtable.save_contacts(job_id, contacts)
    if result["success"]:
        await airtable.mark_contacts_found(job_id)
    return result


@mcp.tool()
async def update_contact_status(contact_id: str, status: str, fields: dict = None) -> dict:
    """
    Update a contact's outreach status.
    Valid statuses: Ready, Drafted, Approved, Sent, Skipped
    """
    return await airtable.update_contact_status(contact_id, status, fields)


@mcp.tool()
async def save_message_draft(contact_id: str, message: str) -> dict:
    """
    Save a drafted message for a contact.
    """
    return await airtable.save_message_draft(contact_id, message)


@mcp.tool()
async def get_contact_with_job(contact_id: str) -> dict:
    """
    Get a contact with its linked job application data.
    Returns full context needed for message generation including resume_postgres_id.
    """
    return await airtable.get_contact_with_job(contact_id)


@mcp.tool()
async def get_active_jobs_for_network_mining() -> dict:
    """
    Get all "In progress" jobs for Farmer pipeline network overlap analysis.
    """
    return await airtable.get_active_jobs_for_network_mining()


# ==================== APOLLO TOOLS ====================

@mcp.tool()
async def find_company_contacts(company_name: str, job_title: str, limit: int = 5) -> dict:
    """
    Search Apollo.io for relevant contacts at a company.
    
    Automatically determines appropriate titles based on job role:
    - Hiring managers (priority 1)
    - Recruiters (priority 2)
    - Team members (priority 3)
    
    Rate limit: 200 searches/day (Apollo free tier)
    """
    return await apollo.find_contacts(company_name, job_title, limit)


# ==================== APIFY TOOLS (v2.0) ====================
# Cost-effective replacement for Apollo using Apify + DeepSeek LLM

@mcp.tool()
async def discover_contacts_for_job(job_id: str, limit: int = 5) -> dict:
    """
    [PRIMARY] Full contact discovery pipeline from an Airtable job_id.
    
    This is the MAIN ENTRY POINT for the Apify-based contact discovery.
    
    Flow:
    1. Fetches job from Airtable (company, Job Position, Job Link, Full Description)
    2. Scrapes Job Link for location
    3. Uses DeepSeek LLM to generate relevant hiring manager titles
       - Much smarter than static mapping for complex titles like:
         "Health Data Analytics Consultant, Payment Model"
    4. Google X-Ray search for LinkedIn profiles
    
    Args:
        job_id: Airtable record ID (e.g., "rec0AH6wTYAWOBEVx")
        limit: Max contacts per category (default 5)
    
    Returns:
        contacts list with linkedin_url, contact_type, priority
        plus title_extraction showing LLM-generated titles
    """
    return await apify.discover_contacts_for_job(
        job_id=job_id,
        airtable_client=airtable,
        limit=limit
    )


@mcp.tool()
async def scrape_job_location(job_url: str) -> dict:
    """
    Scrape a job posting URL to extract Location.
    
    Supports: LinkedIn, Greenhouse, Lever, and generic job boards.
    
    Returns:
        location, company, job_title, success status
    """
    return await apify.scrape_job_location(job_url)


@mcp.tool()
async def find_contacts_apify(
    company: str,
    job_position: str,
    job_description: str = "",
    location: str = None,
    limit: int = 5
) -> dict:
    """
    Find contacts at a company using Google X-Ray search (Apify).
    
    Uses DeepSeek LLM to intelligently map job_position to hiring manager titles.
    
    Examples of LLM title extraction:
    - "Health Data Analytics Consultant" -> "Director of Health Analytics", "VP Clinical Analytics"
    - "Software Engineer" -> "Engineering Manager", "VP of Engineering"
    - "Revenue Cycle Business Analyst" -> "Director of Revenue Cycle Operations"
    
    Args:
        company: Company name to search
        job_position: The exact job title (from Airtable's Job Position field)
        job_description: Full JD for better title extraction (optional)
        location: Optional location to filter results (auto-excludes "Remote")
        limit: Max contacts per category
    
    Returns:
        contacts list with linkedin_url, contact_type, priority, location_match
        plus title_extraction showing LLM-generated titles
    """
    return await apify.find_contacts(
        company=company,
        job_position=job_position,
        job_description=job_description,
        location=location,
        limit=limit
    )


# ==================== RESUME TOOLS (v3.0) ====================

@mcp.tool()
async def get_active_resume(job_role: str = None) -> dict:
    """
    [DEPRECATED in v3.0 - use get_tailored_resume with application_id instead]
    
    Fetch a generic resume text from Windmill Postgres.
    Uses crude keyword matching (healthcare, fintech, etc).
    """
    return await resume.get_active_resume(job_role)


@mcp.tool()
async def get_tailored_resume(application_id: int) -> dict:
    """
    [v3.0] Fetch the JD-tailored resume and cold emails for a specific job application.
    
    Uses the linking chain:
      Airtable Resume_Postgres_ID -> generated_resumes.application_id
    
    Args:
        application_id: The job_applications.id (from Airtable's Resume_Postgres_ID field)
    
    Returns:
        tailored_content, final_content, cold_email_recruiter, cold_email_manager,
        cover_letter_content, similarity_score
    """
    return await resume.get_tailored_resume(application_id)


@mcp.tool()
async def get_cold_email(application_id: int, contact_type: str) -> dict:
    """
    [v3.0] Fetch the appropriate pre-generated cold email for a contact type.
    
    Routing:
      hiring_manager -> cold_email_manager
      recruiter      -> cold_email_recruiter
      team_member    -> None (uses final_content as resume_context instead)
    
    Fallback chain if cold email field is empty:
      1. final_content
      2. tailored_content
      3. None (outreach falls back to resume_highlights)
    
    Args:
        application_id: The job_applications.id
        contact_type: "hiring_manager", "recruiter", or "team_member"
    
    Returns:
        cold_email, resume_context, fallback_used, source_field
    """
    return await resume.get_cold_email(application_id, contact_type)


@mcp.tool()
async def check_skill_match(
    job_description: str,
    skill: str = "epic",
    application_id: Optional[int] = None
) -> dict:
    """
    Check if the user's resume contains a skill mentioned in a JD.
    
    Args:
        job_description: The full job description text
        skill: The skill keyword to look for (default: "epic")
        application_id: Optional - if provided, checks the tailored resume instead of generic
    
    Returns:
        requirement_found, skill_found, has_gap, recommendation
    """
    return await resume.check_skill_match(job_description, skill, application_id)


# ==================== v3.0: OUTREACH CONTEXT ORCHESTRATION ====================

@mcp.tool()
async def get_outreach_context(contact_id: str) -> dict:
    """
    [v3.0] Resolve the FULL linking chain in one call. Primary entry point for outreach.
    
    Chain:
      1. Airtable contact -> linked job -> resume_postgres_id
      2. generated_resumes.application_id -> cold_email by contact_type
      3. check_skill_match for epic gap detection
    
    Returns everything needed for generate_message():
      contact, job, cold_email, resume_context, has_epic_gap
    
    This replaces the need for multiple tool calls before generating a message.
    """
    # Step 1: Get contact with linked job
    contact_job = await airtable.get_contact_with_job(contact_id)
    
    if not contact_job.get("success"):
        return {
            "success": False,
            "error": contact_job.get("error", "Failed to fetch contact"),
            "contact": None,
            "job": None
        }
    
    contact = contact_job.get("contact", {})
    job = contact_job.get("job", {})
    
    # Extract key fields
    contact_type = contact.get("contact_type", "team_member")
    resume_postgres_id = job.get("resume_postgres_id")
    job_description = job.get("job_description", "")
    
    # Step 2: Get cold email / resume context if we have an application_id
    cold_email_data = {
        "cold_email": None,
        "resume_context": None,
        "fallback_used": True,
        "source_field": None
    }
    
    if resume_postgres_id:
        try:
            application_id = int(resume_postgres_id)
            cold_email_data = await resume.get_cold_email(application_id, contact_type)
        except (ValueError, TypeError):
            # resume_postgres_id is not a valid int (older jobs)
            cold_email_data["note"] = f"Invalid resume_postgres_id: {resume_postgres_id}"
    
    # Step 3: Epic gap detection
    epic_check = {"has_gap": False}
    if job_description:
        if resume_postgres_id:
            try:
                application_id = int(resume_postgres_id)
                epic_check = await resume.check_skill_match(job_description, "epic", application_id)
            except (ValueError, TypeError):
                epic_check = await resume.check_skill_match(job_description, "epic")
        else:
            epic_check = await resume.check_skill_match(job_description, "epic")
    
    return {
        "success": True,
        "contact": contact,
        "job": job,
        "cold_email": cold_email_data.get("cold_email"),
        "resume_context": cold_email_data.get("resume_context"),
        "fallback_used": cold_email_data.get("fallback_used", True),
        "source_field": cold_email_data.get("source_field"),
        "has_epic_gap": epic_check.get("has_gap", False),
        "epic_recommendation": epic_check.get("recommendation")
    }


# ==================== NETWORK MINING TOOLS (Farmer Pipeline) ====================

@mcp.tool()
async def analyze_network_overlap(csv_content: str, active_jobs: list[dict]) -> dict:
    """
    Cross-reference LinkedIn connections CSV with active job applications.
    Finds "insiders" - existing connections at target companies.
    
    Args:
        csv_content: Raw text content of LinkedIn Connections.csv
        active_jobs: List of jobs with company, role, status, job_id
    
    Returns:
        List of insiders with contact info and job match
    
    NOTE: This is the Farmer pipeline. Only processes "In progress" jobs.
    """
    return network_mining.analyze_network_overlap(csv_content, active_jobs)


@mcp.tool()
async def get_network_stats(csv_content: str) -> dict:
    """
    Get statistics about your LinkedIn network from Connections.csv.
    """
    return network_mining.get_network_stats(csv_content)


@mcp.tool()
async def find_connections_by_company(csv_content: str, company_name: str) -> dict:
    """
    Find all your connections at a specific company.
    """
    return network_mining.find_by_company(csv_content, company_name)


# ==================== OUTREACH MESSAGE TOOLS (v3.0 - 3-Phase) ====================

@mcp.tool()
async def generate_cold_connect_note(
    contact_name: str,
    contact_title: str,
    contact_type: str,
    company: str,
    job_title: str,
    job_description: str = "",
    cold_email_template: Optional[str] = None,
    resume_context: Optional[str] = None,
    resume_highlights: str = ""
) -> dict:
    """
    [v3.0] Generate a LinkedIn Connection Request Note for STRANGERS (Hunter pipeline).
    Uses 3-Phase architecture: Hook (contact title) → Value (cold email) → Ask (soft CTA).
    
    CONSTRAINTS:
    - MAX 300 characters (LinkedIn limit)
    - Handles Epic certification gap automatically
    
    Args:
        contact_name: Full name of the contact
        contact_title: Their actual job title (e.g., "Engineering Manager")
        contact_type: hiring_manager / recruiter / team_member
        company: Company name
        job_title: Role you applied for
        job_description: Full JD text (for Epic detection)
        cold_email_template: Pre-generated cold email from Windmill (optional)
        resume_context: Tailored resume final_content fallback (optional)
        resume_highlights: Legacy fallback context
    """
    return await outreach.generate_cold_connect_note(
        contact_name=contact_name,
        contact_title=contact_title,
        contact_type=contact_type,
        company=company,
        job_title=job_title,
        job_description=job_description,
        cold_email_template=cold_email_template,
        resume_context=resume_context,
        resume_highlights=resume_highlights
    )


@mcp.tool()
async def generate_warm_dm(
    contact_name: str,
    company: str,
    target_role: str,
    connected_date: str,
    contact_title: Optional[str] = None,
    contact_type: str = "team_member",
    cold_email_template: Optional[str] = None,
    resume_context: Optional[str] = None,
    resume_highlights: Optional[str] = None
) -> dict:
    """
    [v3.0] Generate a LinkedIn Direct Message for EXISTING connections (Farmer pipeline).
    Uses 3-Phase architecture: Hook (warm reconnect) → Value (cold email) → Ask (soft CTA).
    
    NO character limit (DMs don't have the 300 char restriction).
    
    Args:
        contact_name: Full name
        company: Their current company (your target)
        target_role: Role you applied for
        connected_date: When you connected (from CSV)
        contact_title: Their current title
        contact_type: hiring_manager / recruiter / team_member
        cold_email_template: Pre-generated cold email from Windmill
        resume_context: Tailored resume fallback
        resume_highlights: Legacy fallback context
    """
    return await outreach.generate_warm_dm(
        contact_name=contact_name,
        company=company,
        target_role=target_role,
        connected_date=connected_date,
        contact_title=contact_title,
        contact_type=contact_type,
        cold_email_template=cold_email_template,
        resume_context=resume_context,
        resume_highlights=resume_highlights
    )


@mcp.tool()
async def refine_message(
    current_message: str,
    edit_instruction: str,
    max_length: int = None,
    pipeline: str = "hunter"
) -> dict:
    """
    Refine/edit an existing message based on user feedback.
    
    Args:
        current_message: The draft to edit
        edit_instruction: User's feedback (e.g., "make it shorter")
        max_length: Character limit (295 for hunter, None for farmer)
        pipeline: "hunter" or "farmer"
    """
    return await outreach.refine_message(
        current_message=current_message,
        edit_instruction=edit_instruction,
        max_length=max_length,
        pipeline=pipeline
    )


@mcp.tool()
async def generate_message(
    contact_name: str,
    company: str,
    job_title: str,
    contact_title: str = "",
    contact_type: str = "team_member",
    connection_degree: str = "2nd",
    contact_source: str = "apollo",
    job_description: str = "",
    cold_email_template: Optional[str] = None,
    resume_context: Optional[str] = None,
    resume_highlights: str = "",
    connected_date: Optional[str] = None
) -> dict:
    """
    [v3.0] Unified message generator that routes to Hunter or Farmer pipeline.
    Uses 3-Phase architecture with cold email templates.
    
    Automatically determines pipeline based on:
    - connection_degree: "1st" → Farmer, "2nd"/"3rd" → Hunter
    - contact_source: "csv_import" → Farmer, "apollo" → Hunter
    
    For full automation, use get_outreach_context first to resolve the linking chain,
    then pass the results here.
    """
    return await outreach.generate_message(
        contact_name=contact_name,
        company=company,
        job_title=job_title,
        contact_title=contact_title,
        contact_type=contact_type,
        connection_degree=connection_degree,
        contact_source=contact_source,
        job_description=job_description,
        cold_email_template=cold_email_template,
        resume_context=resume_context,
        resume_highlights=resume_highlights,
        connected_date=connected_date
    )


# ==================== DISCORD TOOLS ====================

@mcp.tool()
async def send_approval_request(
    contact_id: str,
    contact_name: str,
    contact_type: str,
    company: str,
    job_title: str,
    linkedin_url: str,
    message_draft: str,
    connection_degree: str = "2nd",
    pipeline: str = "hunter"
) -> dict:
    """
    Send an approval request to Discord with rich embed.
    
    Returns thread_id for follow-up conversation.
    """
    return await discord.send_approval(
        contact_id=contact_id,
        contact_name=contact_name,
        contact_type=contact_type,
        company=company,
        job_title=job_title,
        linkedin_url=linkedin_url,
        message_draft=message_draft,
        connection_degree=connection_degree,
        pipeline=pipeline
    )


@mcp.tool()
async def wait_for_discord_response(thread_id: str, timeout_seconds: int = 300) -> dict:
    """
    Wait for user response in Discord thread.
    
    Returns: action (approve/skip/edit) and any edit instructions.
    """
    return await discord.wait_for_response(thread_id, timeout_seconds)


@mcp.tool()
async def send_discord_update(thread_id: str, message: str) -> dict:
    """
    Send a follow-up message in a Discord thread.
    Used during conversational editing.
    """
    return await discord.send_message(thread_id, message)


@mcp.tool()
async def mark_contact_approved(contact_id: str, final_message: str, linkedin_url: str) -> dict:
    """
    Mark a contact as approved, save final message.
    Returns the LinkedIn URL for manual sending.
    """
    await airtable.mark_contact_approved(contact_id, final_message)
    
    return {
        "success": True,
        "action": "approved",
        "linkedin_url": linkedin_url,
        "message": final_message,
        "instruction": "Open the LinkedIn URL and send the connection request with this message."
    }


# ==================== SECOND BRAIN TOOLS (v1.0) ====================

@mcp.tool()
async def classify_thought(content: str) -> dict:
    """
    Classify a raw thought/message from Discord #brain-dump.
    
    Categories: Knowledge, Project, People, Task, Inbox.
    Returns structured data with confidence score and extracted entities.
    """
    return await second_brain.classify_thought(content)


@mcp.tool()
async def route_to_notion(
    content: str,
    category: str,
    title: str,
    tags: list[str] = None,
    priority: str = "medium"
) -> dict:
    """
    Route classified content to the appropriate Notion database.
    """
    return await second_brain.route_to_notion(
        content=content,
        category=category,
        title=title,
        tags=tags,
        priority=priority
    )


@mcp.tool()
async def process_chat_file(file_content: str, source_platform: str = "auto") -> dict:
    """
    Ingest a raw chat export (Claude/ChatGPT) and extract 'Knowledge Atoms'.
    
    1. Cleans conversational fluff
    2. Extracts key concepts/decisions
    3. Returns atoms ready for Notion/Postgres
    """
    return await chat_ingest.process_chat_file(file_content, source_platform)

# ==================== CONTENT FACTORY TOOLS (v2.0) ====================

@mcp.tool()
async def generate_content_package(knowledge_uuid: str) -> dict:
    """
    [PRIMARY] Full Content Factory pipeline: FETCH → GENERATE → SAVE.
    
    Takes a Knowledge DB page ID and:
    1. Fetches the source content from Notion
    2. Generates a viral LinkedIn post + 60-second video script
    3. Saves drafts to Content Pipeline DB with source relation
    
    Args:
        knowledge_uuid: Notion page ID from Knowledge DB
    
    Returns:
        linkedin_draft, video_script, content_page_id, source_title
    """
    return await content_tools.generate_content_package(knowledge_uuid)


# ==================== LEGACY CONTENT TOOLS ====================


@mcp.tool()
async def notes_to_linkedin_post(
    notes_content: str,
    topic: str,
    tone: str = "professional",
    include_hashtags: bool = True
) -> dict:
    """
    Transform study notes or chat logs into an engaging LinkedIn post.
    """
    return await content_tools.notes_to_linkedin_post(
        notes_content=notes_content,
        topic=topic,
        tone=tone,
        include_hashtags=include_hashtags
    )


@mcp.tool()
async def generate_video_script(
    notes_content: str,
    topic: str,
    duration_minutes: int = 3,
    style: str = "educational"
) -> dict:
    """
    Generate a video script (YouTube/LinkedIn) from notes.
    """
    return await content_tools.generate_video_script(
        notes_content=notes_content,
        topic=topic,
        duration_minutes=duration_minutes,
        style=style
    )


# ==================== RUN SERVER ====================

# Global reference to the asyncio event loop (set when MCP starts)
_event_loop = None


async def _route_action(action: str, params: dict) -> dict:
    """
    Route an n8n webhook action to the corresponding MCP tool function.
    
    This is the dispatcher that maps action strings from n8n HTTP Request nodes
    to actual async tool implementations.
    """
    # ---- Workflow 1: Job Application Monitor ----
    if action == "get_jobs_needing_contacts":
        status = params.get("status", "In progress")
        return await airtable.get_jobs_needing_contacts(status)

    elif action == "discover_contacts_for_job":
        job_id = params.get("job_id")
        limit = params.get("limit", 5)
        if not job_id:
            return {"success": False, "error": "job_id is required"}
        return await apify.discover_contacts_for_job(
            job_id=job_id,
            airtable_client=airtable,
            limit=limit
        )

    elif action == "save_contacts_to_airtable":
        job_id = params.get("job_id")
        contacts = params.get("contacts", [])
        if not job_id:
            return {"success": False, "error": "job_id is required"}
        if not contacts:
            return {"success": False, "error": "contacts list is required"}
        result = await airtable.save_contacts(job_id, contacts)
        if result.get("success"):
            await airtable.mark_contacts_found(job_id)
        return result

    # ---- Workflow 2: Content Factory Pipeline ----
    elif action == "generate_content_package":
        knowledge_uuid = params.get("knowledge_uuid")
        if not knowledge_uuid:
            return {"success": False, "error": "knowledge_uuid is required"}
        return await content_tools.generate_content_package(knowledge_uuid)

    # ---- Workflow 3: Daily Brain Dump Summary ----
    elif action == "classify_thought":
        content = params.get("content", "")
        if not content:
            return {"success": False, "error": "content is required"}
        return await second_brain.classify_thought(content)

    elif action == "route_to_notion":
        return await second_brain.route_to_notion(
            content=params.get("content", ""),
            category=params.get("category", "Inbox"),
            title=params.get("title", "Untitled"),
            tags=params.get("tags"),
            priority=params.get("priority", "medium")
        )

    # ---- Workflow 4: Outreach Message Generator ----
    elif action == "get_outreach_context":
        contact_id = params.get("contact_id")
        if not contact_id:
            return {"success": False, "error": "contact_id is required"}
        # Reuse the full orchestration from the MCP tool
        contact_job = await airtable.get_contact_with_job(contact_id)
        if not contact_job.get("success"):
            return contact_job

        contact = contact_job.get("contact", {})
        job = contact_job.get("job", {})
        contact_type = contact.get("contact_type", "team_member")
        resume_postgres_id = job.get("resume_postgres_id")
        job_description = job.get("job_description", "")

        cold_email_data = {"cold_email": None, "resume_context": None,
                           "fallback_used": True, "source_field": None}
        if resume_postgres_id:
            try:
                app_id = int(resume_postgres_id)
                cold_email_data = await resume.get_cold_email(app_id, contact_type)
            except (ValueError, TypeError):
                pass

        epic_check = {"has_gap": False}
        if job_description:
            try:
                app_id = int(resume_postgres_id) if resume_postgres_id else None
                epic_check = await resume.check_skill_match(
                    job_description, "epic", app_id
                )
            except (ValueError, TypeError):
                epic_check = await resume.check_skill_match(job_description, "epic")

        return {
            "success": True, "contact": contact, "job": job,
            "cold_email": cold_email_data.get("cold_email"),
            "resume_context": cold_email_data.get("resume_context"),
            "has_epic_gap": epic_check.get("has_gap", False)
        }

    elif action == "generate_outreach" or action == "generate_message":
        return await outreach.generate_message(
            contact_name=params.get("contact_name", ""),
            company=params.get("company", ""),
            job_title=params.get("job_title", ""),
            contact_title=params.get("contact_title", ""),
            contact_type=params.get("contact_type", "team_member"),
            connection_degree=params.get("connection_degree", "2nd"),
            contact_source=params.get("contact_source", "apollo"),
            job_description=params.get("job_description", ""),
            cold_email_template=params.get("cold_email_template"),
            resume_context=params.get("resume_context"),
            resume_highlights=params.get("resume_highlights", ""),
            connected_date=params.get("connected_date")
        )

    # ---- Workflow 5: Network Mining ----
    elif action == "analyze_network_overlap":
        csv_content = params.get("csv_content", "")
        active_jobs = params.get("active_jobs", [])
        if not csv_content:
            return {"success": False, "error": "csv_content is required"}
        return network_mining.analyze_network_overlap(csv_content, active_jobs)

    elif action == "get_active_jobs_for_network_mining":
        return await airtable.get_active_jobs_for_network_mining()

    # ---- Airtable Utilities ----
    elif action == "get_job_details":
        job_id = params.get("job_id")
        if not job_id:
            return {"success": False, "error": "job_id is required"}
        return await airtable.get_job_details(job_id)

    elif action == "update_contact_status":
        contact_id = params.get("contact_id")
        status = params.get("status")
        if not contact_id or not status:
            return {"success": False, "error": "contact_id and status are required"}
        return await airtable.update_contact_status(
            contact_id, status, params.get("fields")
        )

    else:
        return {
            "success": False,
            "error": f"Unknown action: {action}",
            "available_actions": [
                "get_jobs_needing_contacts", "discover_contacts_for_job",
                "save_contacts_to_airtable", "generate_content_package",
                "classify_thought", "route_to_notion",
                "get_outreach_context", "generate_outreach", "generate_message",
                "analyze_network_overlap", "get_active_jobs_for_network_mining",
                "get_job_details", "update_contact_status"
            ]
        }


def run_health_server():
    """HTTP server for Docker health checks and n8n webhooks on port 8080."""
    import asyncio
    import threading
    import json
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status": "healthy", "service": "titan-mcp-server"}')
            elif self.path == "/actions":
                # Convenience endpoint: list all available actions
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                actions = {
                    "workflow_1_job_monitor": [
                        "get_jobs_needing_contacts",
                        "discover_contacts_for_job",
                        "save_contacts_to_airtable"
                    ],
                    "workflow_2_content_factory": [
                        "generate_content_package"
                    ],
                    "workflow_3_brain_dump": [
                        "classify_thought",
                        "route_to_notion"
                    ],
                    "workflow_4_outreach": [
                        "get_outreach_context",
                        "generate_outreach",
                        "generate_message"
                    ],
                    "workflow_5_network_mining": [
                        "analyze_network_overlap",
                        "get_active_jobs_for_network_mining"
                    ],
                    "utilities": [
                        "get_job_details",
                        "update_contact_status"
                    ]
                }
                self.wfile.write(json.dumps(actions, indent=2).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            """Handle n8n webhook triggers — routes action to MCP tools."""
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)

            try:
                payload = json.loads(body) if body else {}

                if self.path == "/webhook/n8n-trigger":
                    action = payload.get("action")
                    if not action:
                        self.send_response(400)
                        self.send_header("Content-type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({
                            "success": False,
                            "error": "Missing 'action' field in request body"
                        }).encode())
                        return

                    # Extract params (everything except 'action')
                    params = {k: v for k, v in payload.items() if k != "action"}

                    # Run the async tool via the event loop
                    global _event_loop
                    if _event_loop is None:
                        # Fallback: create a new loop for this thread
                        result = asyncio.run(_route_action(action, params))
                    else:
                        # Use the MCP server's event loop
                        import concurrent.futures
                        future = asyncio.run_coroutine_threadsafe(
                            _route_action(action, params), _event_loop
                        )
                        result = future.result(timeout=300)  # 5 min timeout

                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(result, default=str).encode())

                else:
                    self.send_response(404)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"error": "Endpoint not found"}')

            except Exception as e:
                self.send_response(500)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "success": False,
                    "error": str(e),
                    "error_type": type(e).__name__
                }).encode())

        def log_message(self, format, *args):
            pass  # Suppress logs

    server = HTTPServer(("0.0.0.0", 8080), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print("Health server running on port 8080 (health checks + n8n webhooks)")


if __name__ == "__main__":
    import sys

    # Check if running in Docker (no tty = no stdin)
    if os.environ.get("MCP_TRANSPORT", "stdio") == "sse" or not sys.stdin.isatty():
        # SSE transport for Docker / server deployment
        # Runs as HTTP server on port 8080
        print("Starting MCP server with SSE transport on port 8080...")
        mcp.run(transport="sse", host="0.0.0.0", port=8080)
    else:
        # stdio transport for local Claude Desktop
        import asyncio
        loop = asyncio.new_event_loop()
        _event_loop = loop

        def _start_mcp():
            asyncio.set_event_loop(loop)
            run_health_server()
            mcp.run()

        _start_mcp()

