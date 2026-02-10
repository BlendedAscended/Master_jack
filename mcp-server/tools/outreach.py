# mcp-server/tools/outreach.py
"""
Titan Outreach Tools (v3.0) — 3-Phase Message Architecture

- Hunter Pipeline: Cold connect notes for strangers (300 char limit)
- Farmer Pipeline: Warm DMs for existing connections (no limit)
- 3-Phase structure: Hook (respect contact) → Value (cold email/resume) → Ask (soft CTA)
- Epic certification detection preserved
- Uses pre-generated cold emails from Windmill's generated_resumes table
"""

import os
from typing import Optional
from openai import OpenAI


class OutreachTools:
    def __init__(self):
        self.client = OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url="https://api.deepseek.com"
        )

    # ==================== HELPER: BUILD VALUE SECTION ====================

    def _build_value_section(
        self,
        cold_email_template: Optional[str],
        resume_context: Optional[str],
        resume_highlights: str
    ) -> str:
        """Build the value context for the user prompt based on what's available."""
        if cold_email_template:
            return f"Cold email template to condense (DO NOT copy verbatim — distill the core value):\n{cold_email_template[:800]}"
        elif resume_context:
            return f"Resume context to draw from:\n{resume_context[:500]}"
        elif resume_highlights:
            return f"Background highlights:\n{resume_highlights[:500]}"
        return "No specific background provided. Focus on genuine interest in the role."

    def _format_contact_type(self, contact_type: str) -> str:
        """Human-readable contact type for prompts."""
        return {
            "hiring_manager": "Hiring Manager",
            "recruiter": "Recruiter",
            "team_member": "Team Member / Peer"
        }.get(contact_type, "Professional")

    # ==================== HUNTER PIPELINE (Cold Outreach) ====================

    async def generate_cold_connect_note(
        self,
        contact_name: str,
        contact_title: str,
        contact_type: str,
        company: str,
        job_title: str,
        job_description: str = "",
        cold_email_template: Optional[str] = None,
        resume_context: Optional[str] = None,
        resume_highlights: str = "",
        max_length: int = 295
    ) -> dict:
        """
        Generate a LinkedIn Connection Request Note for STRANGERS (2nd/3rd degree).
        Uses 3-Phase architecture: Hook → Value → Ask.

        CRITICAL CONSTRAINTS:
        - MAX 300 characters (LinkedIn limit for connection notes)
        - **THE 40-CHAR RULE**: First 40 chars must contain the hook.
        - Target: 250-295 characters for safety

        Args:
            contact_name: Full name of the contact
            contact_title: Their actual job title (e.g., "Engineering Manager")
            contact_type: hiring_manager / recruiter / team_member
            company: Company name
            job_title: The role you applied for
            job_description: Full JD text (for Epic detection)
            cold_email_template: Pre-generated cold email from Windmill (optional)
            resume_context: Tailored resume final_content fallback (optional)
            resume_highlights: Legacy fallback context
            max_length: Character limit (default 295 for safety buffer)

        Returns:
            dict with message, char_count, has_epic_gap, type, pipeline
        """
        first_name = contact_name.split()[0] if contact_name else "there"
        contact_type_display = self._format_contact_type(contact_type)

        # ===== EPIC CERTIFICATION LOGIC =====
        check_text = (resume_context or resume_highlights or "").lower()
        has_epic_requirement = "epic" in job_description.lower() if job_description else False
        has_epic_skill = "epic" in check_text
        has_epic_gap = has_epic_requirement and not has_epic_skill

        # Build 3-Phase system prompt
        system_prompt = f"""You write LinkedIn Connection Request Notes using a 3-Phase structure.
All 3 phases must flow as ONE natural message — no labels, no sections.

HARD LIMIT: {max_length} CHARACTERS. Count every character including spaces and punctuation.

CRITICAL VISIBILITY RULES (VIOLATION = FAILURE):
1. **The Hook Rule:** The FIRST 40 characters MUST contain the specific context/hook.
   - BAD: "Hi Tom, I hope you are doing well." (Wasted preview space)
   - GOOD: "Tom, your post on autonomous agents was..." (Immediate value)
2. **No "Widow" Lines:** Do NOT put a line break after the salutation.
   - BAD: "Hi Tom,\n\nI saw..." (Preview shows only "Hi Tom,")
   - GOOD: "Hi Tom, I saw..." (Preview shows the hook)

PHASE 1 — HOOK (~60 chars):
Reference the contact's specific role ({contact_title}) to show you researched who they are.
- For Hiring Managers: Acknowledge they lead/manage the team for the open role.
- For Recruiters: Acknowledge their role in talent acquisition for the department.
- For Team Members: Acknowledge their expertise in the relevant area.
Show genuine respect for their work. Do NOT use generic greetings.

PHASE 2 — VALUE (~150 chars):
Your specific fit for the role. Extract the SINGLE most compelling point from the
cold email or resume context provided below. Condense it into one punchy sentence.
Do NOT copy verbatim — distill the core value proposition.

PHASE 3 — ASK (~80 chars):
End with a soft, curious question about the team, culture, or their experience.
NOT a referral ask. Genuine curiosity.

RULES:
- NO pleasantries ("Hope you are well", "I hope this finds you")
- NO referral requests ("Can you refer me?", "Would you submit my resume?")
- NO formal closings ("Best regards")
- The message must read as natural conversation, not a template
- Target {max_length} characters. Every character counts."""

        # Epic-specific injection into Phase 2
        if has_epic_gap:
            system_prompt += """

EPIC CERTIFICATION GAP:
The job requires Epic but the user does NOT have it yet.
Weave "working towards Epic certification" naturally into Phase 2.
Brief acknowledgment only — do NOT make it the entire focus."""
        elif has_epic_requirement and has_epic_skill:
            system_prompt += """

EPIC MATCH:
The job requires Epic AND the user has Epic experience.
Mention "Epic" naturally in Phase 2 as a strength."""

        # Build value section for user prompt
        value_section = self._build_value_section(cold_email_template, resume_context, resume_highlights)

        user_prompt = f"""Write a connection request note to:
Contact: {first_name} — {contact_title} ({contact_type_display}) at {company}
Role I applied for: {job_title}

{value_section}

Generate ONLY the message text. No quotes, no labels, no explanation.
Max {max_length} characters. All 3 phases in one flowing message."""

        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=150,
            temperature=0.6
        )

        message = response.choices[0].message.content.strip()

        # Remove any quotes the model might have added
        message = message.strip('"\'')

        # ENFORCE character limit
        if len(message) > max_length:
            truncated = message[:max_length]
            last_period = truncated.rfind('.')
            last_question = truncated.rfind('?')
            cut_point = max(last_period, last_question)
            if cut_point > max_length * 0.6:
                message = truncated[:cut_point + 1]
            else:
                message = truncated[:max_length - 3] + "..."

        return {
            "success": True,
            "message": message,
            "char_count": len(message),
            "max_allowed": max_length,
            "has_epic_gap": has_epic_gap,
            "type": "cold_connect_note",
            "pipeline": "hunter"
        }

    # ==================== FARMER PIPELINE (Warm Outreach) ====================

    async def generate_warm_dm(
        self,
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
        Generate a LinkedIn Direct Message for EXISTING connections (1st degree).
        Uses 3-Phase architecture: Hook → Value → Ask.
        Also uses the 40-char hook rule for mobile notification visibility.

        NO CHARACTER LIMIT (DMs don't have the 300 char restriction).

        Args:
            contact_name: Full name of the contact
            company: Company they work at (your target)
            target_role: The role you applied for at their company
            connected_date: When you connected (from CSV)
            contact_title: Their current job title (if known)
            contact_type: hiring_manager / recruiter / team_member
            cold_email_template: Pre-generated cold email from Windmill (optional)
            resume_context: Tailored resume fallback (optional)
            resume_highlights: Legacy fallback context

        Returns:
            dict with message, char_count, type, pipeline
        """
        first_name = contact_name.split()[0] if contact_name else "there"
        contact_type_display = self._format_contact_type(contact_type)
        title_text = f" ({contact_title})" if contact_title else ""

        # Build value section
        value_section = self._build_value_section(cold_email_template, resume_context, resume_highlights or "")

        system_prompt = f"""You write LinkedIn DMs to existing connections using a 3-Phase structure.
No character limit. Keep it 3-5 sentences total — casual and warm.
All 3 phases flow as ONE natural message — no labels, no sections.

CRITICAL VISIBILITY RULE:
- The FIRST 40 characters must explain WHY you are messaging.
- Do NOT start with "Hi {first_name}, how are you?" -> The user will ignore the notification.
- START with context: "Hi {first_name}, I saw your team is hiring..."

PHASE 1 — HOOK (1 sentence):
Warm, casual opener. Reference that they're at {company}{title_text}.
Show you know who they are and respect their role.
If connected date is known ({connected_date}), reference it naturally if recent.
Style: "Hey {first_name}!" — casual, not corporate.

PHASE 2 — VALUE (1-2 sentences):
Share that you applied to {target_role} at their company.
Use the cold email or resume context to briefly mention your most relevant
qualification. Adapt to casual DM tone — do NOT paste the cold email verbatim.
Be specific about what makes you a fit, not vague.

PHASE 3 — ASK (1 sentence):
End with a genuine question about their experience at the company,
the team culture, or what they enjoy about working there.
NOT a referral ask. Curious and conversational.

RULES:
- Casual tone — like texting a professional acquaintance
- NO formal closings ("Best regards", "Sincerely")
- NO referral requests ("Can you put in a word?")
- NO pleasantries ("Hope you are well")"""

        user_prompt = f"""Write a DM to:
Contact: {first_name} — {contact_title or "Unknown role"} ({contact_type_display}) at {company}
Role I applied for: {target_role}
We connected: {connected_date}

{value_section}

Generate ONLY the message. No quotes, no labels."""

        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=400,
            temperature=0.7
        )

        message = response.choices[0].message.content.strip().strip('"\'')

        return {
            "success": True,
            "message": message,
            "char_count": len(message),
            "type": "warm_dm",
            "pipeline": "farmer"
        }

    # ==================== MESSAGE REFINEMENT ====================

    async def refine_message(
        self,
        current_message: str,
        edit_instruction: str,
        max_length: Optional[int] = None,
        pipeline: str = "hunter"
    ) -> dict:
        """
        Refine/edit an existing message based on user feedback.
        Used during conversational editing loop in Discord.

        Args:
            current_message: The draft to edit
            edit_instruction: User's feedback (e.g., "make it shorter", "mention FHIR")
            max_length: Character limit (None for DMs, 295 for connection notes)
            pipeline: "hunter" or "farmer" to determine constraints

        Returns:
            dict with revised message
        """
        if pipeline == "hunter" and max_length is None:
            max_length = 295

        constraint_text = f"MAXIMUM {max_length} characters." if max_length else "No character limit."

        system_prompt = f"""You edit LinkedIn messages based on user feedback.

{constraint_text}

Rules:
- Apply the edit instruction precisely
- Maintain the original 3-phase structure (Hook → Value → Ask)
- **MAINTAIN THE 40-CHAR HOOK**: Ensure the start of the message remains punchy and visible.
- Maintain the original intent and tone
- Return ONLY the edited message, nothing else
- No quotes around the message"""

        user_prompt = f"""Current message:
{current_message}

Edit instruction: {edit_instruction}

Provide the revised message:"""

        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=200,
            temperature=0.7
        )

        message = response.choices[0].message.content.strip().strip('"\'')

        # Enforce limit if specified
        if max_length and len(message) > max_length:
            message = message[:max_length - 3] + "..."

        return {
            "success": True,
            "message": message,
            "char_count": len(message),
            "max_allowed": max_length,
            "pipeline": pipeline
        }

    # ==================== HELPER: DETECT MESSAGE TYPE ====================

    def determine_pipeline(
        self,
        connection_degree: str,
        contact_source: str
    ) -> str:
        """
        Determine which pipeline to use based on contact metadata.

        Returns: "hunter" or "farmer"
        """
        if connection_degree == "1st" or contact_source == "csv_import":
            return "farmer"
        return "hunter"

    # ==================== UNIFIED ENTRY POINT ====================

    async def generate_message(
        self,
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
        Unified entry point that routes to the appropriate pipeline.

        Determines Hunter vs Farmer based on connection_degree and contact_source.
        Passes 3-Phase context (cold email template, contact title) to the pipeline.
        """
        pipeline = self.determine_pipeline(connection_degree, contact_source)

        if pipeline == "farmer":
            return await self.generate_warm_dm(
                contact_name=contact_name,
                company=company,
                target_role=job_title,
                connected_date=connected_date or "Unknown",
                contact_title=contact_title,
                contact_type=contact_type,
                cold_email_template=cold_email_template,
                resume_context=resume_context,
                resume_highlights=resume_highlights
            )
        else:
            return await self.generate_cold_connect_note(
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
