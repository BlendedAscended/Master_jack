# mcp-server/tools/discord_tools.py
"""
Discord Approval Interface Tools

Provides human-in-the-loop approval for outreach messages via Discord.
Features:
- Rich embeds for message preview
- Threaded conversations for editing
- Reaction-based approve/skip/edit
- Timeout handling
"""

import os
import asyncio
from typing import Optional
import discord
from discord import Embed, Color


class DiscordTools:
    def __init__(self):
        self.token = os.environ.get("DISCORD_BOT_TOKEN")
        self.channel_id = int(os.environ.get("DISCORD_CHANNEL_ID", "0"))
        self.user_id = int(os.environ.get("DISCORD_USER_ID", "0"))
        
        if not self.token:
            raise ValueError("DISCORD_BOT_TOKEN environment variable not set")
        
        # Discord client will be initialized on first use
        self._client = None
        self._pending_responses = {}
    
    def _create_embed(
        self,
        contact_name: str,
        contact_type: str,
        company: str,
        job_title: str,
        linkedin_url: str,
        message_draft: str,
        connection_degree: str = "2nd",
        pipeline: str = "hunter"
    ) -> Embed:
        """Create a rich embed for the approval message."""
        
        # Color based on pipeline
        color = Color.blue() if pipeline == "hunter" else Color.green()
        
        # Title based on pipeline type
        if pipeline == "hunter":
            title = f"👔 Cold Connect: {contact_name}"
        else:
            title = f"💬 Warm DM: {contact_name}"
        
        embed = Embed(title=title, color=color)
        
        # Company and role
        embed.add_field(
            name="Company",
            value=company,
            inline=True
        )
        embed.add_field(
            name="Role Applied For",
            value=job_title,
            inline=True
        )
        
        # Contact info
        embed.add_field(
            name="Contact Type",
            value=contact_type.replace("_", " ").title(),
            inline=True
        )
        embed.add_field(
            name="Connection",
            value=f"{connection_degree} Degree",
            inline=True
        )
        if pipeline == "hunter":
            embed.add_field(
                name="Source",
                value="Apollo.io",
                inline=True
            )
        else:
            embed.add_field(
                name="Source",
                value="LinkedIn CSV",
                inline=True
            )
        
        # The message draft
        char_count = len(message_draft)
        char_status = "✅" if char_count <= 300 else "⚠️"
        
        embed.add_field(
            name=f"📝 Draft ({char_count} chars) {char_status}",
            value=f"```\n{message_draft}\n```",
            inline=False
        )
        
        # LinkedIn URL
        embed.add_field(
            name="🔗 LinkedIn",
            value=linkedin_url if linkedin_url else "Not available",
            inline=False
        )
        
        # Footer with instructions
        embed.set_footer(text="Reply: approve / skip / edit [instructions]")
        
        return embed
    
    async def send_approval(
        self,
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
        Creates a thread for followup conversation.
        
        Returns:
            dict with thread_id for follow-up, and message_id
        """
        import httpx
        
        embed = self._create_embed(
            contact_name=contact_name,
            contact_type=contact_type,
            company=company,
            job_title=job_title,
            linkedin_url=linkedin_url,
            message_draft=message_draft,
            connection_degree=connection_degree,
            pipeline=pipeline
        )
        
        # Send via Discord webhook/API
        async with httpx.AsyncClient(timeout=30) as client:
            # Create the message
            response = await client.post(
                f"https://discord.com/api/v10/channels/{self.channel_id}/messages",
                headers={
                    "Authorization": f"Bot {self.token}",
                    "Content-Type": "application/json"
                },
                json={
                    "content": f"<@{self.user_id}> New outreach ready for review:",
                    "embeds": [embed.to_dict()]
                }
            )
            
            if response.status_code not in [200, 201]:
                return {
                    "success": False,
                    "error": f"Discord API error: {response.status_code} - {response.text}"
                }
            
            message_data = response.json()
            message_id = message_data["id"]
            
            # Create a thread for conversation
            thread_response = await client.post(
                f"https://discord.com/api/v10/channels/{self.channel_id}/messages/{message_id}/threads",
                headers={
                    "Authorization": f"Bot {self.token}",
                    "Content-Type": "application/json"
                },
                json={
                    "name": f"Review: {contact_name} @ {company}"[:100],
                    "auto_archive_duration": 1440  # 24 hours
                }
            )
            
            if thread_response.status_code in [200, 201]:
                thread_data = thread_response.json()
                thread_id = thread_data["id"]
            else:
                thread_id = None
            
            # Store pending response
            self._pending_responses[contact_id] = {
                "message_id": message_id,
                "thread_id": thread_id,
                "contact_name": contact_name,
                "message_draft": message_draft,
                "pipeline": pipeline
            }
            
            return {
                "success": True,
                "message_id": message_id,
                "thread_id": thread_id,
                "contact_id": contact_id
            }
    
    async def wait_for_response(
        self,
        thread_id: str,
        timeout_seconds: int = 300
    ) -> dict:
        """
        Wait for user response in Discord thread.
        
        Returns:
            dict with action (approve/skip/edit) and any edit instructions
        """
        import httpx
        
        start_time = asyncio.get_event_loop().time()
        last_message_id = None
        
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                # Check timeout
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout_seconds:
                    return {
                        "success": False,
                        "action": "timeout",
                        "error": f"No response after {timeout_seconds} seconds"
                    }
                
                # Fetch messages from thread
                params = {"limit": 10}
                if last_message_id:
                    params["after"] = last_message_id
                
                response = await client.get(
                    f"https://discord.com/api/v10/channels/{thread_id}/messages",
                    headers={"Authorization": f"Bot {self.token}"},
                    params=params
                )
                
                if response.status_code != 200:
                    await asyncio.sleep(2)
                    continue
                
                messages = response.json()
                
                for msg in reversed(messages):
                    # Skip bot messages
                    if msg.get("author", {}).get("bot"):
                        continue
                    
                    content = msg.get("content", "").lower().strip()
                    last_message_id = msg["id"]
                    
                    # Parse response
                    if content == "approve":
                        return {
                            "success": True,
                            "action": "approve"
                        }
                    elif content == "skip":
                        return {
                            "success": True,
                            "action": "skip"
                        }
                    elif content.startswith("edit"):
                        instruction = content[4:].strip()
                        return {
                            "success": True,
                            "action": "edit",
                            "instruction": instruction or "make it better"
                        }
                
                # Poll every 2 seconds
                await asyncio.sleep(2)
    
    async def send_message(
        self,
        thread_id: str,
        message: str
    ) -> dict:
        """
        Send a follow-up message in a Discord thread.
        Used during conversational editing.
        """
        import httpx
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"https://discord.com/api/v10/channels/{thread_id}/messages",
                headers={
                    "Authorization": f"Bot {self.token}",
                    "Content-Type": "application/json"
                },
                json={"content": message}
            )
            
            if response.status_code in [200, 201]:
                return {"success": True, "message_id": response.json()["id"]}
            else:
                return {
                    "success": False,
                    "error": f"Failed to send message: {response.status_code}"
                }
    
    async def send_revised_draft(
        self,
        thread_id: str,
        new_message: str,
        char_count: int,
        pipeline: str = "hunter"
    ) -> dict:
        """
        Send a revised draft message in the thread.
        """
        char_limit = 300 if pipeline == "hunter" else "∞"
        char_status = "✅" if (pipeline != "hunter" or char_count <= 300) else "⚠️"
        
        formatted = f"""**Revised ({char_count} chars) {char_status}:**
```
{new_message}
```
Reply: approve / skip / edit [instructions]"""
        
        return await self.send_message(thread_id, formatted)
    
    async def send_approval_confirmation(
        self,
        thread_id: str,
        linkedin_url: str,
        final_message: str
    ) -> dict:
        """
        Send confirmation after approval with copy-paste instructions.
        """
        confirmation = f"""✅ **Approved!**
📋 Message ready to send

🔗 **Open:** {linkedin_url}
→ Click "Connect" → "Add a note" → Paste:

```
{final_message}
```"""
        
        return await self.send_message(thread_id, confirmation)
    
    async def send_skip_confirmation(
        self,
        thread_id: str,
        contact_name: str
    ) -> dict:
        """
        Send confirmation after skipping a contact.
        """
        return await self.send_message(
            thread_id,
            f"⏭️ Skipped {contact_name}. Moving to next contact."
        )
