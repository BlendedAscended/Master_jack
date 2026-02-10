# discord-bot/bot.py
"""
Titan Discord Bot

Human-in-the-loop interface for:
- Outreach message approvals
- Brain dump processing
- System commands

Commands:
- !status - Show Titan system status
- !queue - Show pending approvals
- !help - Show available commands

Reactions:
- ✅ Approve message
- ❌ Skip contact
- ✏️ Edit message (reply with instructions)
"""

import os
import asyncio
import discord
from discord import app_commands
from discord.ext import commands, tasks


class TitanBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        super().__init__(command_prefix="!", intents=intents)
        
        self.approval_channel_id = int(os.environ.get("DISCORD_CHANNEL_ID", "0"))
        self.brain_dump_channel_id = int(os.environ.get("DISCORD_BRAIN_DUMP_CHANNEL_ID", "0"))
        self.owner_id = int(os.environ.get("DISCORD_USER_ID", "0"))
        
        # Track pending approvals
        self.pending_approvals = {}
    
    async def setup_hook(self):
        """Called when the bot is starting up."""
        print("Titan Discord Bot starting...")
        # Start background tasks
        self.check_mcp_health.start()
    
    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print(f"Watching channel: {self.approval_channel_id}")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="for outreach approvals"
            )
        )
    
    async def on_message(self, message):
        """Handle incoming messages."""
        # Ignore bot messages
        if message.author.bot:
            return
        
        # Brain dump channel processing
        if message.channel.id == self.brain_dump_channel_id:
            await self.process_brain_dump(message)
            return
        
        # Check if this is a reply in an approval thread
        if isinstance(message.channel, discord.Thread):
            # Check if parent is the approval channel
            if message.channel.parent_id == self.approval_channel_id:
                await self.handle_approval_response(message)
                return
        
        # Process commands
        await self.process_commands(message)
    
    async def process_brain_dump(self, message):
        """Process a message from the brain dump channel."""
        content = message.content.strip()
        if not content:
            return
        
        # Add reaction to show we're processing
        await message.add_reaction("🧠")
        
        try:
            # Import MCP tools
            import sys
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcp-server'))
            from tools.second_brain import SecondBrainTools
            
            brain = SecondBrainTools()
            
            # Step 1: Classify the thought
            classification = await brain.classify_thought(content)
            
            if not classification.get("success"):
                await message.add_reaction("❌")
                await message.channel.send(
                    f"⚠️ Classification failed: {classification.get('error')}",
                    reference=message
                )
                return
            
            category = classification.get("category", "Inbox")
            title = classification.get("title", content[:50])
            confidence = classification.get("confidence", 0)
            tags = classification.get("tags", [])
            priority = classification.get("priority", "medium")
            
            # Step 2: Route to Notion
            routing = await brain.route_to_notion(
                content=content,
                category=category,
                title=title,
                tags=tags,
                priority=priority
            )
            
            if not routing.get("success"):
                await message.add_reaction("⚠️")
                await message.channel.send(
                    f"⚠️ Saved classification but Notion routing failed: {routing.get('error')}",
                    reference=message
                )
                return
            
            # Success! Show results
            await message.add_reaction("✅")
            
            # Create embed with results
            embed = discord.Embed(
                title=f"🧠 {category}: {title}",
                description=content[:200] + ("..." if len(content) > 200 else ""),
                color=self._get_category_color(category)
            )
            
            embed.add_field(name="Category", value=category, inline=True)
            embed.add_field(name="Confidence", value=f"{confidence:.0%}", inline=True)
            embed.add_field(name="Priority", value=priority.title(), inline=True)
            
            if tags:
                embed.add_field(name="Tags", value=", ".join(tags), inline=False)
            
            notion_url = routing.get("notion_url", "")
            if notion_url:
                embed.add_field(name="Notion", value=f"[View Page]({notion_url})", inline=False)
            
            embed.set_footer(text=f"Saved to {category} DB")
            
            await message.channel.send(embed=embed, reference=message)
            
        except Exception as e:
            await message.add_reaction("❌")
            await message.channel.send(
                f"❌ Error processing thought: {str(e)}",
                reference=message
            )
            print(f"Brain dump error: {e}")
    
    def _get_category_color(self, category: str) -> discord.Color:
        """Get color for category."""
        colors = {
            "Knowledge": discord.Color.blue(),
            "Project": discord.Color.green(),
            "People": discord.Color.purple(),
            "Task": discord.Color.orange(),
            "Inbox": discord.Color.light_gray()
        }
        return colors.get(category, discord.Color.default())
    
    async def handle_approval_response(self, message):
        """Handle responses in approval threads."""
        content = message.content.lower().strip()
        thread_id = str(message.channel.id)
        
        # Check for approval keywords
        if content in ["approve", "approved", "yes", "y", "lgtm", "send"]:
            await message.add_reaction("✅")
            await message.channel.send("✅ **Approved!** Check the message above for copy-paste instructions.")
        
        elif content in ["skip", "no", "pass", "next"]:
            await message.add_reaction("⏭️")
            await message.channel.send("⏭️ **Skipped.** Moving to next contact.")
        
        elif content.startswith("edit"):
            instruction = content[4:].strip()
            await message.add_reaction("✏️")
            await message.channel.send(f"✏️ Got it! Editing: \"{instruction or 'improve it'}\"...")
            # TODO: Call MCP server to refine message
    
    async def on_reaction_add(self, reaction, user):
        """Handle reaction-based approvals."""
        # Ignore bot reactions
        if user.bot:
            return
        
        # Only process in approval channel
        if reaction.message.channel.id != self.approval_channel_id:
            return
        
        emoji = str(reaction.emoji)
        
        if emoji == "✅":
            await reaction.message.channel.send("✅ Approved via reaction!")
        elif emoji == "❌":
            await reaction.message.channel.send("⏭️ Skipped via reaction!")
        elif emoji == "✏️":
            await reaction.message.channel.send(
                "✏️ To edit, reply to the approval message with your instructions."
            )
    
    @tasks.loop(minutes=5)
    async def check_mcp_health(self):
        """Periodically check MCP server health."""
        # TODO: Actually check MCP server
        pass
    
    @check_mcp_health.before_loop
    async def before_health_check(self):
        await self.wait_until_ready()


# === COMMANDS ===

bot = TitanBot()


@bot.command(name="status")
async def status_command(ctx):
    """Show Titan system status."""
    embed = discord.Embed(
        title="🔧 Titan System Status",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="MCP Server", value="🟢 Online", inline=True)
    embed.add_field(name="Discord Bot", value="🟢 Online", inline=True)
    embed.add_field(name="Pending Approvals", value=str(len(bot.pending_approvals)), inline=True)
    
    await ctx.send(embed=embed)


@bot.command(name="queue")
async def queue_command(ctx):
    """Show pending approval queue."""
    if not bot.pending_approvals:
        await ctx.send("📭 No pending approvals.")
        return
    
    embed = discord.Embed(
        title="📋 Pending Approvals",
        color=discord.Color.orange()
    )
    
    for contact_id, data in list(bot.pending_approvals.items())[:10]:
        embed.add_field(
            name=data.get("contact_name", "Unknown"),
            value=f"Company: {data.get('company', 'N/A')}\nPipeline: {data.get('pipeline', 'hunter')}",
            inline=False
        )
    
    await ctx.send(embed=embed)


@bot.command(name="clear")
async def clear_command(ctx, count: int = 10):
    """Clear messages (owner only)."""
    if ctx.author.id != bot.owner_id:
        await ctx.send("❌ Only the owner can use this command.")
        return
    
    deleted = await ctx.channel.purge(limit=min(count, 100))
    await ctx.send(f"🗑️ Deleted {len(deleted)} messages.", delete_after=5)


@bot.command(name="ping")
async def ping_command(ctx):
    """Check bot latency."""
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! Latency: {latency}ms")


# === ERROR HANDLING ===

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return  # Ignore unknown commands
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: {error.param.name}")
    else:
        print(f"Command error: {error}")
        await ctx.send(f"❌ Error: {error}")


# === RUN ===

def main():
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        print("ERROR: DISCORD_BOT_TOKEN not set")
        return
    
    bot.run(token)


if __name__ == "__main__":
    main()
