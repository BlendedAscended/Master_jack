# mcp-server/tools/resume.py
"""
Resume Fetching Tools (v3.0)

Connects to Windmill Postgres to fetch JD-tailored resumes and pre-generated
cold emails from the `generated_resumes` table.

Linking chain:
  Airtable Resume_Postgres_ID -> job_applications.id -> generated_resumes.application_id

v3.0 changes:
- get_tailored_resume(): Fetches exact JD-tailored resume by application_id
- get_cold_email(): Routes to cold_email_manager or cold_email_recruiter by contact_type
- Legacy methods (get_active_resume, get_resume_summary) kept for backward compat
"""

import os
from typing import Optional
import asyncpg


class ResumeTools:
    def __init__(self):
        self.db_url = os.environ.get("WINDMILL_DB_URL")
        if not self.db_url:
            raise ValueError("WINDMILL_DB_URL environment variable not set")
    
    async def get_active_resume(
        self,
        job_role: Optional[str] = None,
        version_tag: Optional[str] = None
    ) -> dict:
        """
        Fetch the most relevant resume text from Windmill Postgres.
        
        Args:
            job_role: Optional job title to match against resume versions
            version_tag: Optional specific version (e.g., "healthcare", "fintech")
        
        Returns:
            dict with full_text, version, skills, and metadata
        """
        conn = await asyncpg.connect(self.db_url)
        try:
            # If specific version requested
            if version_tag:
                query = """
                    SELECT id, full_text, version, skills, created_at
                    FROM resumes
                    WHERE version = $1
                    ORDER BY created_at DESC
                    LIMIT 1
                """
                row = await conn.fetchrow(query, version_tag)
            
            # Smart matching based on job role keywords
            elif job_role:
                job_role_lower = job_role.lower()
                
                # Determine best version based on keywords
                if any(kw in job_role_lower for kw in ['healthcare', 'health', 'medical', 'epic', 'fhir', 'claims']):
                    version_match = 'healthcare'
                elif any(kw in job_role_lower for kw in ['fintech', 'finance', 'payment', 'banking']):
                    version_match = 'fintech'
                elif any(kw in job_role_lower for kw in ['ml', 'machine learning', 'ai', 'data science']):
                    version_match = 'ml_data_science'
                else:
                    version_match = 'general'
                
                query = """
                    SELECT id, full_text, version, skills, created_at
                    FROM resumes
                    WHERE version = $1
                    ORDER BY created_at DESC
                    LIMIT 1
                """
                row = await conn.fetchrow(query, version_match)
                
                # Fallback to most recent if no version match
                if not row:
                    query = """
                        SELECT id, full_text, version, skills, created_at
                        FROM resumes
                        ORDER BY created_at DESC
                        LIMIT 1
                    """
                    row = await conn.fetchrow(query)
            
            # Default: just get the latest
            else:
                query = """
                    SELECT id, full_text, version, skills, created_at
                    FROM resumes
                    ORDER BY created_at DESC
                    LIMIT 1
                """
                row = await conn.fetchrow(query)
            
            if row:
                return {
                    "success": True,
                    "resume_id": str(row['id']),
                    "full_text": row['full_text'],
                    "version": row['version'],
                    "skills": row['skills'] if row['skills'] else [],
                    "created_at": str(row['created_at']),
                    "has_epic": "epic" in row['full_text'].lower() if row['full_text'] else False
                }
            else:
                return {
                    "success": False,
                    "error": "No resume found in database",
                    "full_text": "",
                    "skills": []
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Database error: {str(e)}",
                "full_text": "",
                "skills": []
            }
        finally:
            await conn.close()
    
    async def get_resume_summary(
        self,
        job_id: str
    ) -> dict:
        """
        Fetch the pre-generated resume summary for a specific job application.
        This is stored in Airtable's Resume_Summary field, but may also be
        cached in Postgres for faster access.
        
        Args:
            job_id: The Airtable record ID of the job application
        
        Returns:
            dict with summary text
        """
        conn = await asyncpg.connect(self.db_url)
        try:
            # Check if we have a cached summary for this job
            query = """
                SELECT resume_summary, generated_resume_text
                FROM job_applications
                WHERE airtable_id = $1
                LIMIT 1
            """
            row = await conn.fetchrow(query, job_id)
            
            if row and row['resume_summary']:
                return {
                    "success": True,
                    "summary": row['resume_summary'],
                    "full_resume": row['generated_resume_text'] or ""
                }
            else:
                # Fallback: return generic summary from latest resume
                fallback = await self.get_active_resume()
                if fallback['success']:
                    # Extract first 500 chars as summary
                    text = fallback['full_text']
                    summary = text[:500] + "..." if len(text) > 500 else text
                    return {
                        "success": True,
                        "summary": summary,
                        "full_resume": text,
                        "note": "Using fallback (no job-specific summary found)"
                    }
                return {
                    "success": False,
                    "error": "No resume summary found",
                    "summary": ""
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Database error: {str(e)}",
                "summary": ""
            }
        finally:
            await conn.close()
    
    # ==================== v3.0: TAILORED RESUME + COLD EMAILS ====================

    async def get_tailored_resume(
        self,
        application_id: int
    ) -> dict:
        """
        Fetch the JD-tailored resume and cold emails for a specific job application.

        Uses the linking chain:
          Airtable Resume_Postgres_ID -> generated_resumes.application_id

        Args:
            application_id: The job_applications.id (from Airtable's Resume_Postgres_ID)

        Returns:
            dict with tailored_content, final_content, cold_email_recruiter,
            cold_email_manager, cover_letter_content, similarity_score
        """
        conn = await asyncpg.connect(self.db_url)
        try:
            query = """
                SELECT
                    id, application_id, tailored_content, final_content,
                    cold_email_recruiter, cold_email_manager,
                    cover_letter_content, similarity_score,
                    version_1_planned, version_2_naive, version_grounded,
                    generated_at
                FROM generated_resumes
                WHERE application_id = $1
                ORDER BY generated_at DESC
                LIMIT 1
            """
            row = await conn.fetchrow(query, application_id)

            if row:
                return {
                    "success": True,
                    "resume_id": row["id"],
                    "application_id": row["application_id"],
                    "tailored_content": row["tailored_content"] or "",
                    "final_content": row["final_content"] or "",
                    "cold_email_recruiter": row["cold_email_recruiter"] or "",
                    "cold_email_manager": row["cold_email_manager"] or "",
                    "cover_letter_content": row["cover_letter_content"] or "",
                    "similarity_score": row["similarity_score"],
                    "generated_at": str(row["generated_at"]) if row["generated_at"] else None
                }
            else:
                return {
                    "success": False,
                    "error": f"No generated resume found for application_id {application_id}"
                }

        except Exception as e:
            return {
                "success": False,
                "error": f"Database error: {str(e)}"
            }
        finally:
            await conn.close()

    async def get_cold_email(
        self,
        application_id: int,
        contact_type: str
    ) -> dict:
        """
        Fetch the appropriate pre-generated cold email for a contact type.

        Routing:
          hiring_manager -> cold_email_manager
          recruiter      -> cold_email_recruiter
          team_member    -> None (uses final_content as resume_context instead)

        Fallback chain if cold email field is empty:
          1. final_content
          2. tailored_content
          3. None (outreach.py falls back to resume_highlights)

        Args:
            application_id: The job_applications.id
            contact_type: "hiring_manager", "recruiter", or "team_member"

        Returns:
            dict with cold_email, resume_context, fallback_used, source_field
        """
        resume_data = await self.get_tailored_resume(application_id)

        if not resume_data.get("success"):
            return {
                "success": True,
                "cold_email": None,
                "resume_context": None,
                "fallback_used": True,
                "source_field": None,
                "note": resume_data.get("error", "No generated resume found")
            }

        # Route by contact type
        cold_email = None
        source_field = None

        if contact_type == "hiring_manager":
            cold_email = resume_data.get("cold_email_manager") or None
            source_field = "cold_email_manager"
        elif contact_type == "recruiter":
            cold_email = resume_data.get("cold_email_recruiter") or None
            source_field = "cold_email_recruiter"
        # team_member: no cold email by design, skip to fallback

        # If we have a cold email, return it
        if cold_email:
            return {
                "success": True,
                "cold_email": cold_email,
                "resume_context": resume_data.get("final_content") or "",
                "fallback_used": False,
                "source_field": source_field
            }

        # Fallback chain: final_content -> tailored_content -> None
        resume_context = (
            resume_data.get("final_content")
            or resume_data.get("tailored_content")
            or None
        )

        return {
            "success": True,
            "cold_email": None,
            "resume_context": resume_context,
            "fallback_used": True,
            "source_field": "final_content" if resume_data.get("final_content") else "tailored_content"
        }

    # ==================== SKILL MATCHING ====================

    async def check_skill_match(
        self,
        job_description: str,
        skill_to_check: str = "epic",
        application_id: Optional[int] = None
    ) -> dict:
        """
        Check if the user's resume contains a specific skill mentioned in a JD.

        Args:
            job_description: The full job description text
            skill_to_check: The skill keyword to look for (default: "epic")
            application_id: Optional - if provided, checks the tailored resume instead

        Returns:
            dict with requirement_found, skill_found, has_gap
        """
        # Use tailored resume if application_id provided, else fall back to generic
        if application_id:
            resume_data = await self.get_tailored_resume(application_id)
            resume_text = resume_data.get("final_content") or resume_data.get("tailored_content") or ""
        else:
            resume_data = await self.get_active_resume()
            resume_text = resume_data.get("full_text", "")

        jd_lower = job_description.lower()
        resume_lower = resume_text.lower()
        skill_lower = skill_to_check.lower()
        
        requirement_found = skill_lower in jd_lower
        skill_found = skill_lower in resume_lower
        
        return {
            "skill": skill_to_check,
            "requirement_found": requirement_found,
            "skill_found": skill_found,
            "has_gap": requirement_found and not skill_found,
            "recommendation": (
                f"JD requires '{skill_to_check}' but resume doesn't mention it. "
                "Address this gap in outreach."
            ) if requirement_found and not skill_found else None
        }
