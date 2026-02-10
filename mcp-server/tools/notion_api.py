# mcp-server/tools/notion_api.py
"""
Notion API Client (Async)

Provides async methods for interacting with Notion databases.
Used by SecondBrain and ContentEngine for reading/writing pages.

Uses the official notion-client library with httpx for async.
"""

import os
from typing import Optional
import httpx


class NotionClient:
    """Async Notion API client using httpx directly."""
    
    def __init__(self):
        self.api_key = os.getenv("NOTION_API_KEY")
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        # 6-Database Architecture
        self.databases = {
            "inbox": os.getenv("NOTION_INBOX_ID"),
            "knowledge": os.getenv("NOTION_KNOWLEDGE_ID"),
            "projects": os.getenv("NOTION_PROJECTS_ID"),
            "tasks": os.getenv("NOTION_TASKS_ID"),
            "people": os.getenv("NOTION_PEOPLE_ID"),
            "content": os.getenv("NOTION_CONTENT_ID")
        }
    
    async def get_page(self, page_id: str) -> dict:
        """
        Retrieve a Notion page by ID.
        
        Args:
            page_id: The UUID of the page (with or without dashes)
        
        Returns:
            dict with page properties and content
        """
        async with httpx.AsyncClient() as client:
            # Get page metadata
            page_resp = await client.get(
                f"{self.base_url}/pages/{page_id}",
                headers=self.headers
            )
            
            if page_resp.status_code != 200:
                return {
                    "success": False,
                    "error": f"Failed to fetch page: {page_resp.text}",
                    "status_code": page_resp.status_code
                }
            
            page_data = page_resp.json()
            
            # Get page content (blocks)
            blocks_resp = await client.get(
                f"{self.base_url}/blocks/{page_id}/children",
                headers=self.headers
            )
            
            blocks = []
            if blocks_resp.status_code == 200:
                blocks = blocks_resp.json().get("results", [])
            
            # Extract text content from blocks
            content_text = self._extract_text_from_blocks(blocks)
            
            # Extract title from properties
            title = self._extract_title(page_data.get("properties", {}))
            
            return {
                "success": True,
                "page_id": page_id,
                "title": title,
                "content": content_text,
                "properties": page_data.get("properties", {}),
                "url": page_data.get("url", ""),
                "created_time": page_data.get("created_time"),
                "last_edited_time": page_data.get("last_edited_time")
            }
    
    def _extract_title(self, properties: dict) -> str:
        """Extract title from Notion page properties."""
        # Common title field names
        for field in ["Name", "Title", "title", "name"]:
            if field in properties:
                prop = properties[field]
                if prop.get("type") == "title":
                    title_arr = prop.get("title", [])
                    if title_arr:
                        return "".join([t.get("plain_text", "") for t in title_arr])
        return "Untitled"
    
    def _extract_text_from_blocks(self, blocks: list) -> str:
        """Extract plain text content from Notion blocks."""
        text_parts = []
        
        for block in blocks:
            block_type = block.get("type", "")
            
            if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", 
                             "bulleted_list_item", "numbered_list_item", "quote"]:
                rich_text = block.get(block_type, {}).get("rich_text", [])
                text = "".join([t.get("plain_text", "") for t in rich_text])
                if text:
                    text_parts.append(text)
            
            elif block_type == "code":
                code_text = block.get("code", {}).get("rich_text", [])
                text = "".join([t.get("plain_text", "") for t in code_text])
                if text:
                    text_parts.append(f"```\n{text}\n```")
        
        return "\n\n".join(text_parts)
    
    async def create_page(
        self,
        database_key: str,
        title: str,
        properties: Optional[dict] = None,
        content_blocks: Optional[list] = None,
        relations: Optional[dict] = None
    ) -> dict:
        """
        Create a new page in a Notion database.
        
        Args:
            database_key: Key from self.databases (e.g., "content", "knowledge")
            title: Page title
            properties: Additional properties to set
            content_blocks: List of block objects for page content
            relations: Dict mapping property names to page IDs for relations
        
        Returns:
            dict with created page info
        """
        database_id = self.databases.get(database_key)
        if not database_id:
            return {
                "success": False,
                "error": f"Unknown database key: {database_key}. Available: {list(self.databases.keys())}"
            }
        
        # Build properties
        page_properties = {
            "Name": {
                "title": [{"text": {"content": title}}]
            }
        }
        
        # Add custom properties
        if properties:
            for key, value in properties.items():
                if isinstance(value, str):
                    # Assume rich_text for strings
                    page_properties[key] = {
                        "rich_text": [{"text": {"content": value}}]
                    }
                elif isinstance(value, dict):
                    # Pass through as-is (for select, status, etc.)
                    page_properties[key] = value
        
        # Add relations
        if relations:
            for prop_name, page_ids in relations.items():
                if isinstance(page_ids, str):
                    page_ids = [page_ids]
                page_properties[prop_name] = {
                    "relation": [{"id": pid} for pid in page_ids]
                }
        
        # Build request body
        body = {
            "parent": {"database_id": database_id},
            "properties": page_properties
        }
        
        # Add content blocks if provided
        if content_blocks:
            body["children"] = content_blocks
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/pages",
                headers=self.headers,
                json=body
            )
            
            if resp.status_code not in [200, 201]:
                return {
                    "success": False,
                    "error": f"Failed to create page: {resp.text}",
                    "status_code": resp.status_code
                }
            
            result = resp.json()
            
            return {
                "success": True,
                "page_id": result.get("id"),
                "url": result.get("url"),
                "title": title
            }
    
    async def query_database(
        self,
        database_key: str,
        filter_obj: Optional[dict] = None,
        sorts: Optional[list] = None,
        page_size: int = 10
    ) -> dict:
        """
        Query a Notion database.
        
        Args:
            database_key: Key from self.databases
            filter_obj: Notion filter object
            sorts: Notion sorts array
            page_size: Max results to return
        
        Returns:
            dict with results list
        """
        database_id = self.databases.get(database_key)
        if not database_id:
            return {
                "success": False,
                "error": f"Unknown database key: {database_key}"
            }
        
        body = {"page_size": page_size}
        if filter_obj:
            body["filter"] = filter_obj
        if sorts:
            body["sorts"] = sorts
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/databases/{database_id}/query",
                headers=self.headers,
                json=body
            )
            
            if resp.status_code != 200:
                return {
                    "success": False,
                    "error": f"Query failed: {resp.text}",
                    "status_code": resp.status_code
                }
            
            data = resp.json()
            results = data.get("results", [])
            
            # Simplify results
            simplified = []
            for page in results:
                simplified.append({
                    "id": page.get("id"),
                    "title": self._extract_title(page.get("properties", {})),
                    "url": page.get("url"),
                    "created_time": page.get("created_time"),
                    "properties": page.get("properties", {})
                })
            
            return {
                "success": True,
                "results": simplified,
                "count": len(simplified),
                "has_more": data.get("has_more", False)
            }
    
    def make_rich_text_block(self, text: str) -> dict:
        """Helper to create a paragraph block with rich text."""
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": text}}]
            }
        }
    
    def make_heading_block(self, text: str, level: int = 2) -> dict:
        """Helper to create a heading block."""
        heading_type = f"heading_{level}"
        return {
            "object": "block",
            "type": heading_type,
            heading_type: {
                "rich_text": [{"type": "text", "text": {"content": text}}]
            }
        }
