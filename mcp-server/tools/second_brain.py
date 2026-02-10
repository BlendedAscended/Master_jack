# mcp-server/tools/second_brain.py
"""
Second Brain Tools (Memory Module)

Captures and classifies thoughts from Discord #brain-dump channel.
Routes content to appropriate Notion databases.

Features:
- Automatic thought classification
- Notion database routing
- Vector embeddings for search
"""

import os
import json
from typing import Optional
from openai import AsyncOpenAI
import asyncpg
import httpx
from tools.vectors import VectorTools


class SecondBrainTools:
    def __init__(self):
        # DeepSeek V3 client for classification (AsyncOpenAI for native async)
        self.client = AsyncOpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com"
        )
        # Local CPU embeddings via fastembed (no API key needed)
        self.vectors = VectorTools()
        self.db_url = os.environ.get("WINDMILL_DB_URL")
        self.notion_token = os.environ.get("NOTION_API_KEY")
    
    # Notion database IDs (6-database architecture)
    NOTION_DBS = {
        "inbox": os.environ.get("NOTION_INBOX_ID"),
        "knowledge": os.environ.get("NOTION_KNOWLEDGE_ID"),
        "projects": os.environ.get("NOTION_PROJECTS_ID"),
        "tasks": os.environ.get("NOTION_TASKS_ID"),
        "people": os.environ.get("NOTION_PEOPLE_ID"),
        "content": os.environ.get("NOTION_CONTENT_ID")
    }
    
    async def classify_thought(
        self,
        content: str
    ) -> dict:
        """
        Classify a brain dump message into categories using DeepSeek V3.

        Categories:
        - Knowledge: Facts, concepts, learnings
        - Project: Project ideas or notes
        - People: Info about a person/contact
        - Task: Action item or to-do
        - Inbox: Everything else (misc thoughts)

        Args:
            content: The raw thought/message

        Returns:
            dict with category, tags, priority, and extraction
        """
        system_prompt = """You are a classification engine. You MUST output ONLY valid JSON.

Classify the user's brain dump message into exactly ONE category.

Valid categories (use these exact strings):
- Knowledge: Facts, concepts, technical learnings, insights
- Task: Action items, to-dos, reminders
- Project: Project ideas, feature notes, implementation thoughts
- People: Information about a person, relationship notes
- Inbox: Everything else that doesn't fit above

Output this exact JSON structure:
{
    "category": "Knowledge | Task | Project | People | Inbox",
    "tags": ["tag1", "tag2"],
    "priority": "high | medium | low",
    "title": "brief title (5 words max)",
    "extracted_entities": {
        "people": [],
        "companies": [],
        "technologies": [],
        "dates": []
    }
}

Rules:
- category MUST be one of: Knowledge, Task, Project, People, Inbox
- tags: 1-3 lowercase single-word tags
- priority: high (urgent/time-sensitive), medium (important), low (reference)
- title: max 5 words summarizing the note
- Output ONLY the JSON object. No markdown, no explanation."""

        try:
            response = await self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content}
                ],
                max_tokens=200,
                temperature=0.3,
                response_format={"type": "json_object"}
            )

            classification = json.loads(response.choices[0].message.content)

            # Validate category is one of the expected values
            valid_categories = {"Knowledge", "Task", "Project", "People", "Inbox"}
            if classification.get("category") not in valid_categories:
                classification["category"] = "Inbox"

            return {
                "success": True,
                **classification,
                "original_content": content[:500]
            }
        except (json.JSONDecodeError, KeyError):
            # Fallback: if DeepSeek returns malformed JSON, safe-route to Inbox
            return {
                "success": True,
                "category": "Inbox",
                "title": "Unprocessed Note",
                "tags": [],
                "priority": "low",
                "extracted_entities": {"people": [], "companies": [], "technologies": [], "dates": []},
                "original_content": content[:500]
            }
        except Exception as e:
            return {
                "success": False,
                "category": "Inbox",
                "title": "Unprocessed Note",
                "error": str(e)
            }
    
    async def route_to_notion(
        self,
        content: str,
        category: str,
        title: str,
        tags: Optional[list[str]] = None,
        priority: str = "medium"
    ) -> dict:
        """
        Route classified content to the appropriate Notion database.
        
        Args:
            content: The content to store
            category: Category from classify_thought
            title: Brief title
            tags: Optional tags
            priority: high/medium/low
        
        Returns:
            dict with Notion page ID
        """
        if not self.notion_token:
            return {"success": False, "error": "Notion API key not configured"}
        
        # Map category to database ID (categories are capitalized from classify_thought)
        db_map = {
            "Knowledge": self.NOTION_DBS.get("knowledge"),
            "Project": self.NOTION_DBS.get("projects"),
            "People": self.NOTION_DBS.get("people"),
            "Task": self.NOTION_DBS.get("tasks"),
            "Inbox": self.NOTION_DBS.get("inbox")
        }

        database_id = db_map.get(category, self.NOTION_DBS.get("inbox"))
        
        if not database_id:
            return {"success": False, "error": f"No database configured for category: {category}"}
        
        # Create Notion page with flexible property mapping
        async with httpx.AsyncClient(timeout=30) as client:
            # First, get the database schema to find the title property name
            db_response = await client.get(
                f"https://api.notion.com/v1/databases/{database_id}",
                headers={
                    "Authorization": f"Bearer {self.notion_token}",
                    "Notion-Version": "2022-06-28"
                }
            )
            
            if db_response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Failed to fetch database schema: {db_response.text}"
                }
            
            db_schema = db_response.json()
            properties_schema = db_schema.get("properties", {})
            
            # Find the title property (could be "Name", "Project Name", "Title", etc.)
            title_prop_name = None
            tags_prop_name = None
            
            for prop_name, prop_data in properties_schema.items():
                if prop_data.get("type") == "title":
                    title_prop_name = prop_name
                elif prop_data.get("type") == "multi_select" and "tag" in prop_name.lower():
                    tags_prop_name = prop_name
            
            if not title_prop_name:
                return {
                    "success": False,
                    "error": f"No title property found in {category} database"
                }
            
            # Build properties dynamically
            page_properties = {
                title_prop_name: {
                    "title": [{"text": {"content": title[:100]}}]
                }
            }
            
            # Add tags if the database has a tags property
            if tags_prop_name and tags:
                page_properties[tags_prop_name] = {
                    "multi_select": [{"name": tag} for tag in tags[:5]]
                }
            
            # Create the page
            response = await client.post(
                "https://api.notion.com/v1/pages",
                headers={
                    "Authorization": f"Bearer {self.notion_token}",
                    "Content-Type": "application/json",
                    "Notion-Version": "2022-06-28"
                },
                json={
                    "parent": {"database_id": database_id},
                    "properties": page_properties,
                    "children": [
                        {
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [{"text": {"content": content[:2000]}}]
                            }
                        }
                    ]
                }
            )
            
            if response.status_code in [200, 201]:
                page_data = response.json()
                return {
                    "success": True,
                    "page_id": page_data["id"],
                    "notion_url": page_data.get("url"),
                    "category": category
                }
            else:
                return {
                    "success": False,
                    "error": f"Notion API error: {response.status_code} - {response.text}"
                }
    
    async def vectorize_for_search(
        self,
        content: str,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Create vector embedding and store for semantic search.
        
        Args:
            content: Text to vectorize
            metadata: Optional metadata (category, tags, etc.)
        
        Returns:
            dict with vector ID
        """
        if not self.db_url:
            return {"success": False, "error": "Database not configured"}

        # Generate embedding locally on CPU (384 dimensions, bge-small-en-v1.5)
        embedding = self.vectors.generate_embedding(content[:8000])
        
        # Store in Postgres with pgvector
        conn = await asyncpg.connect(self.db_url)
        try:
            query = """
                INSERT INTO brain_vectors (content, embedding, metadata, created_at)
                VALUES ($1, $2, $3, NOW())
                RETURNING id
            """
            result = await conn.fetchrow(
                query,
                content[:5000],
                embedding,
                json.dumps(metadata) if metadata else None
            )
            
            return {
                "success": True,
                "vector_id": str(result["id"])
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            await conn.close()
    
    async def semantic_search(
        self,
        query: str,
        limit: int = 5
    ) -> dict:
        """
        Search brain content using semantic similarity.
        
        Args:
            query: Search query
            limit: Max results
        
        Returns:
            dict with matching content
        """
        if not self.db_url:
            return {"success": False, "error": "Database not configured", "results": []}

        # Generate query embedding locally on CPU (384 dimensions, bge-small-en-v1.5)
        query_embedding = self.vectors.generate_embedding(query)
        
        conn = await asyncpg.connect(self.db_url)
        try:
            # Cosine similarity search using pgvector
            query_sql = """
                SELECT id, content, metadata, 
                       1 - (embedding <=> $1::vector) as similarity
                FROM brain_vectors
                ORDER BY embedding <=> $1::vector
                LIMIT $2
            """
            rows = await conn.fetch(query_sql, query_embedding, limit)
            
            results = []
            for row in rows:
                results.append({
                    "id": str(row["id"]),
                    "content": row["content"][:500],
                    "similarity": float(row["similarity"]),
                    "metadata": row["metadata"]
                })
            
            return {
                "success": True,
                "query": query,
                "results": results
            }
            
        except Exception as e:
            return {"success": False, "error": str(e), "results": []}
        finally:
            await conn.close()
    
    async def process_brain_dump(
        self,
        content: str
    ) -> dict:
        """
        Full pipeline: classify → route to Notion → vectorize for search.
        
        Args:
            content: Raw brain dump message
        
        Returns:
            dict with all results
        """
        # Step 1: Classify
        classification = await self.classify_thought(content)
        
        if not classification.get("success"):
            return {"success": False, "error": "Classification failed"}
        
        # Step 2: Route to Notion
        notion_result = await self.route_to_notion(
            content=content,
            category=classification["category"],
            title=classification.get("title", "Untitled"),
            tags=classification.get("tags"),
            priority=classification.get("priority", "medium")
        )
        
        # Step 3: Vectorize (parallel, don't wait if it fails)
        vector_result = await self.vectorize_for_search(
            content=content,
            metadata={
                "category": classification["category"],
                "tags": classification.get("tags"),
                "title": classification.get("title")
            }
        )
        
        return {
            "success": True,
            "classification": classification,
            "notion_page": notion_result.get("page_id") if notion_result.get("success") else None,
            "notion_url": notion_result.get("url"),
            "vectorized": vector_result.get("success", False)
        }
