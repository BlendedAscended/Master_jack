# mcp-server/tools/content.py
"""
Content Factory Engine (v2.0)

The "Content Factory" that transforms Knowledge Atoms into publishable content.
Reads from Notion Knowledge DB, generates drafts, writes to Content Pipeline DB.

Architecture:
- FETCH: Read source material from Knowledge DB
- GENERATE: Use DeepSeek V3 to create LinkedIn posts + video scripts
- SAVE: Write drafts to Content Pipeline DB with source relation

Tech Stack:
- LLM: DeepSeek V3 (via openai SDK)
- Embeddings: fastembed (local CPU, no API costs)
- Storage: Notion API (async httpx)
"""

import os
import json
from typing import Optional
from openai import AsyncOpenAI
from tools.notion_api import NotionClient


class ContentEngine:
    """
    Content Factory for transforming knowledge into publishable content.
    
    Workflow:
    1. Fetch source material from Notion Knowledge DB
    2. Generate LinkedIn post + video script with DeepSeek
    3. Save drafts to Content Pipeline DB with source relation
    """
    
    def __init__(self):
        # DeepSeek V3 client
        self.llm = AsyncOpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com"
        )
        self.model = "deepseek-chat"
        
        # Notion client for database operations
        self.notion = NotionClient()
    
    async def generate_content_package(self, knowledge_uuid: str) -> dict:
        """
        Full Content Factory pipeline: FETCH → GENERATE → SAVE.
        
        Args:
            knowledge_uuid: The Notion page ID from Knowledge DB
        
        Returns:
            dict with:
                - linkedin_draft: Generated LinkedIn post
                - video_script: Generated 60-second script
                - content_page_id: ID of created Content Pipeline page
                - source_title: Original knowledge note title
        """
        # ========== STEP 1: FETCH ==========
        source_page = await self.notion.get_page(knowledge_uuid)
        
        if not source_page.get("success"):
            return {
                "success": False,
                "error": f"Failed to fetch source: {source_page.get('error')}",
                "step": "fetch"
            }
        
        source_title = source_page.get("title", "Untitled")
        source_content = source_page.get("content", "")
        
        if not source_content:
            return {
                "success": False,
                "error": "Source page has no content to transform",
                "step": "fetch",
                "source_title": source_title
            }
        
        # ========== STEP 2: GENERATE ==========
        
        # Step 2A: Generate LinkedIn Post
        linkedin_draft = await self._generate_linkedin_post(
            content=source_content,
            topic=source_title
        )
        
        # Step 2B: Generate Video Script
        video_script = await self._generate_video_script(
            content=source_content,
            topic=source_title
        )
        
        # ========== STEP 3: SAVE TO CONTENT PIPELINE ==========
        
        # Build content blocks for the page
        content_blocks = [
            self.notion.make_heading_block("LinkedIn Draft", level=2),
            self.notion.make_rich_text_block(linkedin_draft),
            self.notion.make_heading_block("Video Script (60s)", level=2),
            self.notion.make_rich_text_block(video_script)
        ]
        
        # Create page in Content Pipeline DB
        content_page = await self.notion.create_page(
            database_key="content",
            title=f"Content: {source_title}",
            properties={
                "Status": {"status": {"name": "Drafting"}},
                "Linkedin Draft": linkedin_draft[:2000],  # Corrected casing
                "Video Script": video_script[:2000]       # Casing match
            },
            content_blocks=content_blocks,
            relations={
                "Source Material": [knowledge_uuid]  # Link back to source
            },
            title_property="Title" # Actual field name in DB
        )
        
        if not content_page.get("success"):
            # Still return the generated content even if save fails
            return {
                "success": False,
                "error": f"Generated content but failed to save: {content_page.get('error')}",
                "step": "save",
                "linkedin_draft": linkedin_draft,
                "video_script": video_script,
                "source_title": source_title
            }
        
        return {
            "success": True,
            "content_page_id": content_page.get("page_id"),
            "content_page_url": content_page.get("url"),
            "source_title": source_title,
            "source_id": knowledge_uuid,
            "linkedin_draft": linkedin_draft,
            "video_script": video_script,
            "linkedin_char_count": len(linkedin_draft),
            "video_word_count": len(video_script.split())
        }
    
    async def _generate_linkedin_post(self, content: str, topic: str) -> str:
        """
        Generate a viral-style LinkedIn post from source content.
        
        Style:
        - Strong hook in first line
        - Short paragraphs (1-3 sentences)
        - 3-5 hashtags at end
        - No excessive emojis
        """
        system_prompt = """You are a LinkedIn content strategist who creates viral posts.

STYLE RULES:
- First line MUST be a hook that stops scrolling (question, bold statement, or surprising fact)
- Use SHORT paragraphs (1-3 sentences max)
- Include white space between paragraphs
- Add ONE specific insight or data point from the source
- End with engagement trigger (question or call-to-action)
- Include 3-5 relevant hashtags at the very end
- MAX 2 emojis total (optional)
- Keep under 2000 characters

FORMAT:
[Hook - attention grabbing first line]

[Short paragraph with key insight]

[Another short paragraph]

[Call to action or question]

#hashtag1 #hashtag2 #hashtag3"""

        user_prompt = f"""Topic: {topic}

Source Material:
{content[:3000]}

Create a viral LinkedIn post:"""

        response = await self.llm.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=800,
            temperature=0.7
        )
        
        return response.choices[0].message.content.strip()
    
    async def _generate_video_script(self, content: str, topic: str) -> str:
        """
        Generate a 60-second spoken-word video script (~150 words).
        
        Style:
        - Conversational, punchy delivery
        - [Visual Cue] brackets for editing
        - Natural speaking rhythm with pauses noted
        """
        system_prompt = """You are a video script writer for short-form content (TikTok, LinkedIn Video, Reels).

TARGET: 60 seconds (~150 words spoken)

SCRIPT FORMAT:
[HOOK - 5 seconds]
(Attention-grabbing opener, look at camera)

[MAIN POINT - 40 seconds]
(Core insight, speak conversationally)
[Visual: relevant b-roll or text overlay]

[TAKEAWAY - 15 seconds]
(Single actionable insight + soft CTA)

STYLE RULES:
- Write for SPEAKING, not reading
- Use contractions (don't, you're, it's)
- Include [Visual: description] cues for editing
- Note (pauses) or (emphasis) where needed
- Be punchy - cut filler words
- End with subtle engagement hook"""

        user_prompt = f"""Topic: {topic}

Source Material:
{content[:2000]}

Write a 60-second video script (~150 words):"""

        response = await self.llm.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=500,
            temperature=0.7
        )
        
        return response.choices[0].message.content.strip()
    
    # ========== LEGACY METHODS (for backwards compatibility) ==========
    
    async def notes_to_linkedin_post(
        self,
        notes_content: str,
        topic: str,
        tone: str = "professional",
        include_hashtags: bool = True,
        max_length: int = 3000
    ) -> dict:
        """
        [LEGACY] Direct text-to-LinkedIn conversion.
        For new workflows, use generate_content_package() instead.
        """
        post = await self._generate_linkedin_post(notes_content, topic)
        
        hashtags = []
        if "#" in post:
            for word in post.split():
                if word.startswith("#"):
                    hashtags.append(word)
        
        return {
            "success": True,
            "post": post,
            "char_count": len(post),
            "hashtags": hashtags,
            "topic": topic,
            "tone": tone
        }
    
    async def generate_video_script(
        self,
        notes_content: str,
        topic: str,
        duration_minutes: int = 1,
        style: str = "educational"
    ) -> dict:
        """
        [LEGACY] Direct text-to-script conversion.
        For new workflows, use generate_content_package() instead.
        """
        script = await self._generate_video_script(notes_content, topic)
        word_count = len(script.split())
        
        return {
            "success": True,
            "script": script,
            "word_count": word_count,
            "estimated_duration_minutes": round(word_count / 150, 1),
            "target_duration": duration_minutes,
            "topic": topic,
            "style": style
        }
    
    async def summarize_for_social(
        self,
        content: str,
        platform: str = "linkedin",
        max_length: Optional[int] = None
    ) -> dict:
        """Create platform-specific summaries."""
        platform_limits = {
            "linkedin": 3000,
            "twitter": 280,
            "email": 500
        }
        
        limit = max_length or platform_limits.get(platform, 1000)
        
        response = await self.llm.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": f"Create a {platform} summary under {limit} chars."},
                {"role": "user", "content": f"Summarize:\n\n{content[:3000]}"}
            ],
            max_tokens=500,
            temperature=0.7
        )
        
        summary = response.choices[0].message.content.strip()
        
        return {
            "success": True,
            "summary": summary,
            "char_count": len(summary),
            "platform": platform,
            "max_length": limit
        }


# Alias for backwards compatibility with server.py imports
ContentTools = ContentEngine
