# mcp-server/tools/chat_ingest.py
"""
Chat Ingest Tools (Distiller Module)

Extracts knowledge atoms from AI chat exports (ChatGPT, Claude, etc.).
Chrome extension exports → structured knowledge in Notion.

Features:
- Parse various export formats
- Extract key insights and decisions
- Auto-categorize by topic
- Link related concepts
"""

import os
import re
from typing import Optional
from openai import AsyncOpenAI


class ChatIngestTools:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url="https://api.deepseek.com"
        )
    
    async def parse_chat_export(
        self,
        content: str,
        format_type: str = "markdown"
    ) -> dict:
        """
        Parse a chat export file into structured messages.
        
        Args:
            content: Raw export content
            format_type: "markdown", "json", "text"
        
        Returns:
            dict with parsed messages and metadata
        """
        if format_type == "json":
            import json
            try:
                data = json.loads(content)
                # Handle common JSON export formats
                if isinstance(data, list):
                    messages = data
                elif "messages" in data:
                    messages = data["messages"]
                else:
                    messages = [data]
                
                return {
                    "success": True,
                    "format": "json",
                    "message_count": len(messages),
                    "messages": messages
                }
            except json.JSONDecodeError as e:
                return {
                    "success": False,
                    "error": f"Invalid JSON: {str(e)}"
                }
        
        elif format_type == "markdown":
            # Parse markdown chat format
            # Common patterns: "**User:**", "**Assistant:**", "You:", "AI:"
            messages = []
            current_role = None
            current_content = []
            
            for line in content.split("\n"):
                # Check for role markers
                role_match = re.match(r"^\*?\*?(User|You|Human|Me)\*?\*?:?\s*(.*)$", line, re.IGNORECASE)
                if role_match:
                    if current_role:
                        messages.append({
                            "role": current_role,
                            "content": "\n".join(current_content).strip()
                        })
                    current_role = "user"
                    current_content = [role_match.group(2)] if role_match.group(2) else []
                    continue
                
                assistant_match = re.match(r"^\*?\*?(Assistant|AI|Claude|GPT|Bot)\*?\*?:?\s*(.*)$", line, re.IGNORECASE)
                if assistant_match:
                    if current_role:
                        messages.append({
                            "role": current_role,
                            "content": "\n".join(current_content).strip()
                        })
                    current_role = "assistant"
                    current_content = [assistant_match.group(2)] if assistant_match.group(2) else []
                    continue
                
                # Regular content line
                if current_role:
                    current_content.append(line)
            
            # Don't forget the last message
            if current_role:
                messages.append({
                    "role": current_role,
                    "content": "\n".join(current_content).strip()
                })
            
            return {
                "success": True,
                "format": "markdown",
                "message_count": len(messages),
                "messages": messages
            }
        
        else:  # Plain text
            # Treat as single blob
            return {
                "success": True,
                "format": "text",
                "message_count": 1,
                "messages": [{"role": "unknown", "content": content}]
            }
    
    async def extract_knowledge_atoms(
        self,
        chat_content: str,
        max_atoms: int = 10
    ) -> dict:
        """
        Extract discrete knowledge atoms from a chat conversation.
        
        Atoms include:
        - Key decisions made
        - Code snippets with context
        - Concepts explained
        - Problems solved
        - Resources mentioned
        
        Args:
            chat_content: Full chat content (parsed or raw)
            max_atoms: Maximum atoms to extract
        
        Returns:
            dict with knowledge atoms
        """
        system_prompt = f"""Extract knowledge atoms from this AI chat conversation.

A knowledge atom is a discrete, reusable piece of information:
- A decision and its rationale
- A code pattern with explanation
- A concept definition or insight
- A problem-solution pair
- A useful resource or tool

Extract up to {max_atoms} atoms. For each atom:
1. title: Brief descriptive title
2. type: decision|code|concept|solution|resource
3. content: The extracted knowledge (concise but complete)
4. tags: Relevant keywords
5. importance: high|medium|low

Respond in JSON:
{{
    "atoms": [
        {{
            "title": "...",
            "type": "...",
            "content": "...",
            "tags": ["..."],
            "importance": "..."
        }}
    ],
    "chat_topic": "main topic of the chat",
    "total_messages": "estimated number"
}}"""

        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Extract knowledge from:\n\n{chat_content[:8000]}"}
            ],
            max_tokens=2000,
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        import json
        try:
            result = json.loads(response.choices[0].message.content)
            return {
                "success": True,
                **result
            }
        except json.JSONDecodeError:
            return {
                "success": False,
                "error": "Failed to parse extraction",
                "atoms": []
            }
    
    async def identify_followups(
        self,
        chat_content: str
    ) -> dict:
        """
        Identify any follow-up actions or unresolved items from a chat.
        
        Args:
            chat_content: Chat content
        
        Returns:
            dict with follow-up items
        """
        system_prompt = """Analyze this chat for unresolved items and follow-ups.

Identify:
1. Questions left unanswered
2. Tasks mentioned but not completed
3. Ideas to explore later
4. External research needed
5. Code to write/test

For each item:
- description: What needs to happen
- priority: high|medium|low
- type: question|task|exploration|research|code

Respond in JSON:
{
    "followups": [
        {
            "description": "...",
            "priority": "...",
            "type": "..."
        }
    ],
    "is_complete": true/false
}"""

        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Find follow-ups in:\n\n{chat_content[:8000]}"}
            ],
            max_tokens=500,
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        import json
        try:
            result = json.loads(response.choices[0].message.content)
            return {
                "success": True,
                **result
            }
        except json.JSONDecodeError:
            return {
                "success": False,
                "followups": [],
                "is_complete": None
            }
    
    async def process_chat_file(
        self,
        file_content: str,
        file_name: str = "chat_export.md"
    ) -> dict:
        """
        Full pipeline: parse → extract atoms → identify followups.
        
        Args:
            file_content: Raw file content
            file_name: File name for format detection
        
        Returns:
            dict with complete processing results
        """
        # Determine format from filename
        if file_name.endswith(".json"):
            format_type = "json"
        elif file_name.endswith(".md"):
            format_type = "markdown"
        else:
            format_type = "text"
        
        # Parse
        parse_result = await self.parse_chat_export(file_content, format_type)
        
        if not parse_result.get("success"):
            return parse_result
        
        # For extraction, we need the raw content
        chat_text = file_content
        
        # Extract atoms
        atoms_result = await self.extract_knowledge_atoms(chat_text)
        
        # Identify followups
        followups_result = await self.identify_followups(chat_text)
        
        return {
            "success": True,
            "file_name": file_name,
            "format": format_type,
            "message_count": parse_result.get("message_count", 0),
            "chat_topic": atoms_result.get("chat_topic", "Unknown"),
            "atoms": atoms_result.get("atoms", []),
            "followups": followups_result.get("followups", []),
            "is_complete": followups_result.get("is_complete")
        }
