# mcp-server/tools/engagement.py
"""
Engagement Tools (Pundit Module)

Draft authentic comments on VIP LinkedIn posts.
Maintains a "Stance Database" to ensure consistent viewpoints.

Features:
- VIP post monitoring integration (via Apify)
- Stance-based comment generation
- Consistent voice across interactions
"""

import os
from typing import Optional
from openai import OpenAI
import asyncpg


class EngagementTools:
    def __init__(self):
        self.client = OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url="https://api.deepseek.com"
        )
        self.db_url = os.environ.get("WINDMILL_DB_URL")
    
    async def get_stance(
        self,
        topic: str
    ) -> dict:
        """
        Retrieve the user's stance on a specific topic.
        
        Used to ensure consistent viewpoints in comments.
        
        Args:
            topic: Topic keyword or category
        
        Returns:
            dict with stance, examples, and tone guidance
        """
        if not self.db_url:
            return {
                "success": False,
                "error": "Database not configured",
                "stance": None
            }
        
        conn = await asyncpg.connect(self.db_url)
        try:
            # Search for matching stance
            query = """
                SELECT topic, stance, examples, tone, created_at
                FROM stance_db
                WHERE LOWER(topic) LIKE LOWER($1)
                ORDER BY created_at DESC
                LIMIT 1
            """
            row = await conn.fetchrow(query, f"%{topic}%")
            
            if row:
                return {
                    "success": True,
                    "topic": row["topic"],
                    "stance": row["stance"],
                    "examples": row["examples"] or [],
                    "tone": row["tone"] or "professional"
                }
            else:
                return {
                    "success": True,
                    "topic": topic,
                    "stance": None,
                    "note": "No stance found. Generate a balanced response."
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "stance": None
            }
        finally:
            await conn.close()
    
    async def store_stance(
        self,
        topic: str,
        stance: str,
        examples: Optional[list[str]] = None,
        tone: str = "professional"
    ) -> dict:
        """
        Store or update the user's stance on a topic.
        
        Args:
            topic: Topic keyword
            stance: The user's position/viewpoint
            examples: Supporting points or examples
            tone: Preferred tone for this topic
        
        Returns:
            dict with confirmation
        """
        if not self.db_url:
            return {"success": False, "error": "Database not configured"}
        
        conn = await asyncpg.connect(self.db_url)
        try:
            # Upsert stance
            query = """
                INSERT INTO stance_db (topic, stance, examples, tone, created_at)
                VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT (topic) DO UPDATE
                SET stance = $2, examples = $3, tone = $4, created_at = NOW()
                RETURNING id
            """
            result = await conn.fetchrow(query, topic, stance, examples, tone)
            
            return {
                "success": True,
                "stance_id": str(result["id"]),
                "topic": topic
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            await conn.close()
    
    async def draft_comment(
        self,
        post_content: str,
        post_author: str,
        topic: Optional[str] = None,
        max_length: int = 500
    ) -> dict:
        """
        Generate an authentic comment for a VIP post.
        
        Checks Stance DB if topic matches, otherwise generates
        a thoughtful, balanced response.
        
        Args:
            post_content: The LinkedIn post content
            post_author: Name of the post author
            topic: Optional topic hint for stance lookup
            max_length: Maximum comment length
        
        Returns:
            dict with comment draft
        """
        # Try to get relevant stance
        stance_data = None
        if topic:
            stance_data = await self.get_stance(topic)
        
        # Build system prompt
        system_prompt = f"""You draft authentic LinkedIn comments.

RULES:
- Sound like a real person, not a bot
- Add genuine value (insight, question, or experience)
- NO generic praise ("Great post!", "So true!")
- Keep it concise (under {max_length} characters)
- Match the tone of the original post
- If you disagree, do so respectfully

{"STANCE GUIDANCE:" + chr(10) + stance_data.get('stance', '') if stance_data and stance_data.get('stance') else ""}
{"TONE: " + stance_data.get('tone', 'professional') if stance_data else "TONE: professional"}
"""

        user_prompt = f"""Post by {post_author}:
{post_content[:2000]}

Draft a thoughtful comment:"""

        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=300,
            temperature=0.7
        )
        
        comment = response.choices[0].message.content.strip()
        
        # Enforce length limit
        if len(comment) > max_length:
            comment = comment[:max_length - 3] + "..."
        
        return {
            "success": True,
            "comment": comment,
            "char_count": len(comment),
            "post_author": post_author,
            "stance_used": stance_data.get("topic") if stance_data and stance_data.get("stance") else None
        }
    
    async def analyze_post_topic(
        self,
        post_content: str
    ) -> dict:
        """
        Analyze a post to determine its main topic(s).
        Useful for stance lookup.
        
        Args:
            post_content: The post to analyze
        
        Returns:
            dict with topic, sentiment, and key points
        """
        system_prompt = """Analyze this LinkedIn post and identify:
1. Main topic (one keyword/phrase)
2. Sentiment (positive/negative/neutral)
3. Key points (2-3 bullets)
4. Whether it's controversial or opinion-based

Respond in JSON format:
{
    "topic": "...",
    "sentiment": "...",
    "key_points": ["...", "..."],
    "is_opinion": true/false
}"""

        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": post_content[:2000]}
            ],
            max_tokens=200,
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        import json
        try:
            analysis = json.loads(response.choices[0].message.content)
            return {
                "success": True,
                **analysis
            }
        except json.JSONDecodeError:
            return {
                "success": False,
                "error": "Failed to parse analysis",
                "raw": response.choices[0].message.content
            }
