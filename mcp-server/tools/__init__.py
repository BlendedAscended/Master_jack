# mcp-server/tools/__init__.py
"""
Titan MCP Server - Tool Registry

Exports all tool classes for the MCP server.

Tool Categories:
- Data Access: AirtableTools, ResumeTools
- Discovery: ApolloTools, NetworkMiningTools
- Message Generation: OutreachTools
- Approval: DiscordTools
- Content: ContentTools, EngagementTools
- Knowledge: SecondBrainTools, ChatIngestTools

DEPRECATED in v2.0:
- Neo4j tools (removed)
- Resume atom tools (removed)
"""

from tools.airtable import AirtableTools
from tools.apollo import ApolloTools
from tools.outreach import OutreachTools
from tools.resume import ResumeTools
from tools.network_mining import NetworkMiningTools
from tools.discord_tools import DiscordTools
from tools.content import ContentTools
from tools.engagement import EngagementTools
from tools.second_brain import SecondBrainTools
from tools.chat_ingest import ChatIngestTools

__all__ = [
    # Core tools (Hunter/Farmer pipelines)
    "AirtableTools",
    "ApolloTools",
    "OutreachTools",
    "ResumeTools",
    "NetworkMiningTools",
    
    # Approval interface
    "DiscordTools",
    
    # Content & Engagement
    "ContentTools",
    "EngagementTools",
    
    # Knowledge management
    "SecondBrainTools",
    "ChatIngestTools",
]
