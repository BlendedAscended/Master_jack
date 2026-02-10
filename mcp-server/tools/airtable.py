# mcp-server/tools/airtable.py
"""
Airtable Tools (v2.0)

Handles all Airtable operations for job applications and contacts.

CRITICAL CHANGE (v2.0):
- get_jobs_needing_contacts now ONLY returns "In Progress" jobs
- "To Do" jobs are no longer eligible for outreach
"""

import os
from typing import Optional
import httpx


class AirtableTools:
    def __init__(self):
        self.api_key = os.environ["AIRTABLE_API_KEY"]
        self.base_id = os.environ["AIRTABLE_BASE_ID"]
        self.base_url = f"https://api.airtable.com/v0/{self.base_id}"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    # ==================== JOB APPLICATION TOOLS ====================
    
    async def get_jobs_needing_contacts(
        self,
        status: str = "In progress",  # Note: lowercase 'p' per Airtable
        table_name: str = "Applications"  # Actual table name
    ) -> dict:
        """
        Get job applications that need contact discovery.
        
        CRITICAL: Only fetches "In progress" jobs by default.
        "Todo" jobs are NOT eligible for outreach (v2.0 change).
        
        Filters:
        - Status == "In progress" (or specified status)
        - Job Link is not empty
        - Contacts_Found is false (or empty)
        
        Returns:
            dict with jobs list, each containing id, company, role, jd_text
        """
        # Build filter formula
        # ONLY "In progress" jobs are eligible for outreach
        filter_formula = f"""AND(
            {{Status}} = "{status}",
            {{Job Link}} != "",
            OR({{Contacts_Found}} = FALSE(), {{Contacts_Found}} = "")
        )"""
        
        url = f"{self.base_url}/{table_name}"
        params = {
            "filterByFormula": filter_formula,
            "pageSize": 100
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=self.headers, params=params)
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Airtable API error: {response.text}",
                    "jobs": []
                }
            
            records = response.json().get("records", [])
            
            jobs = []
            for record in records:
                fields = record.get("fields", {})
                jobs.append({
                    "job_id": record["id"],
                    "company": fields.get("Company", ""),
                    "role": fields.get("Job Position", ""),
                    "linkedin_url": fields.get("Job Link", ""),
                    "status": fields.get("Status", ""),
                    "job_description": fields.get("Full Description", ""),
                    "contacts_json": fields.get("Contacts_Json", ""),
                    "drive_link": fields.get("Drive_link", ""),
                    "resume_postgres_id": fields.get("Resume_Postgres_ID", None)
                })
            
            return {
                "success": True,
                "status_filter": status,
                "total_found": len(jobs),
                "jobs": jobs,
                "note": "Only 'In progress' jobs are eligible for outreach (v2.0)"
            }
    
    async def get_job_details(
        self,
        job_id: str,
        table_name: str = "Applications"  # Actual table name
    ) -> dict:
        """
        Get full details of a specific job application.
        
        Returns all fields including Full Description.
        """
        url = f"{self.base_url}/{table_name}/{job_id}"
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=self.headers)
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Job not found or API error: {response.text}"
                }
            
            record = response.json()
            fields = record.get("fields", {})
            
            return {
                "success": True,
                "job_id": record["id"],
                "company": fields.get("Company", ""),
                "role": fields.get("Job Position", ""),
                "linkedin_url": fields.get("Job Link", ""),
                "status": fields.get("Status", ""),
                "job_description": fields.get("Full Description", ""),
                "skill_audit": fields.get("Skill Audit", ""),
                "drive_link": fields.get("Drive_link", ""),
                "contacts_found": fields.get("Contacts_Found", False),
                "resume_postgres_id": fields.get("Resume_Postgres_ID", None)
            }
    
    async def update_job(
        self,
        job_id: str,
        fields: dict,
        table_name: str = "Applications"  # Actual table name
    ) -> dict:
        """
        Update fields on a job application record.
        """
        url = f"{self.base_url}/{table_name}/{job_id}"
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.patch(
                url,
                headers=self.headers,
                json={"fields": fields}
            )
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Update failed: {response.text}"
                }
            
            return {"success": True, "job_id": job_id}
    
    async def mark_contacts_found(
        self,
        job_id: str,
        table_name: str = "Applications"  # Actual table name
    ) -> dict:
        """
        Mark a job as having contacts discovered.
        Sets Contacts_Found = true.
        """
        return await self.update_job(job_id, {"Contacts_Found": True}, table_name)
    
    # ==================== CONTACTS TOOLS ====================
    
    async def get_contacts_ready_for_outreach(
        self,
        statuses: list[str] = None,
        table_name: str = "Contacts"
    ) -> dict:
        """
        Get contacts that are ready for message drafting.
        
        Args:
            statuses: List of statuses to filter by (default: ["Ready"])
        
        Returns:
            dict with contacts list
        """
        if statuses is None:
            statuses = ["Ready"]
        
        # Build OR formula for multiple statuses
        status_conditions = ", ".join([f'{{Outreach_Status}} = "{s}"' for s in statuses])
        filter_formula = f"OR({status_conditions})"
        
        url = f"{self.base_url}/{table_name}"
        params = {
            "filterByFormula": filter_formula,
            "pageSize": 100
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=self.headers, params=params)
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Airtable API error: {response.text}",
                    "contacts": []
                }
            
            records = response.json().get("records", [])
            
            contacts = []
            for record in records:
                fields = record.get("fields", {})
                contacts.append({
                    "contact_id": record["id"],
                    "name": fields.get("Name", ""),
                    "title": fields.get("Title", ""),
                    "linkedin_url": fields.get("LinkedIn_URL", ""),
                    "email": fields.get("Email", ""),
                    "contact_type": fields.get("Contact_Type", ""),
                    "contact_source": fields.get("Contact_Source", "apollo"),
                    "connection_degree": fields.get("Connection_Degree", "2nd"),
                    "priority": fields.get("Priority", 99),
                    "job_id": fields.get("Job_Application", [""])[0] if fields.get("Job_Application") else "",
                    "outreach_status": fields.get("Outreach_Status", ""),
                    "connected_on": fields.get("Connected_On", ""),
                    "message_draft": fields.get("Message_Draft", "")
                })
            
            # Sort by priority
            contacts.sort(key=lambda x: x["priority"])
            
            return {
                "success": True,
                "total_found": len(contacts),
                "contacts": contacts
            }
    
    async def save_contacts(
        self,
        job_id: str,
        contacts: list[dict],
        table_name: str = "Contacts"
    ) -> dict:
        """
        Save discovered contacts to Airtable, linked to the job application.
        
        Each contact should have:
        - name, title, linkedin_url, email (optional)
        - contact_type (hiring_manager, recruiter, team_member)
        - contact_source (apollo, csv_import)
        - connection_degree (1st, 2nd, 3rd)
        - priority (1 = highest)
        - connected_on (for 1st degree connections)
        
        Returns:
            dict with created record IDs
        """
        url = f"{self.base_url}/{table_name}"
        
        created_ids = []
        errors = []
        
        async with httpx.AsyncClient(timeout=30) as client:
            for contact in contacts:
                fields = {
                    "Name": contact.get("name", ""),
                    "Title": contact.get("title", ""),
                    "LinkedIn_URL": contact.get("linkedin_url", ""),
                    "Contact_Type": contact.get("contact_type", "team_member"),
                    "Contact_Source": contact.get("contact_source", "apollo"),
                    "Connection_Degree": contact.get("connection_degree", "2nd"),
                    "Priority": contact.get("priority", 99),
                    "Outreach_Status": "Ready",
                    "Job_Application": [job_id]  # Linked record
                }
                
                # Optional fields
                if contact.get("email"):
                    fields["Email"] = contact["email"]
                if contact.get("connected_on"):
                    fields["Connected_On"] = contact["connected_on"]
                
                response = await client.post(
                    url,
                    headers=self.headers,
                    json={"fields": fields}
                )
                
                if response.status_code == 200:
                    created_ids.append(response.json()["id"])
                else:
                    errors.append({
                        "contact": contact.get("name"),
                        "error": response.text
                    })
        
        return {
            "success": len(errors) == 0,
            "created_count": len(created_ids),
            "created_ids": created_ids,
            "errors": errors
        }
    
    async def update_contact_status(
        self,
        contact_id: str,
        status: str,
        additional_fields: Optional[dict] = None,
        table_name: str = "Contacts"
    ) -> dict:
        """
        Update a contact's outreach status.
        
        Valid statuses: Ready, Drafted, Approved, Sent, Skipped
        """
        url = f"{self.base_url}/{table_name}/{contact_id}"
        
        fields = {"Outreach_Status": status}
        if additional_fields:
            fields.update(additional_fields)
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.patch(
                url,
                headers=self.headers,
                json={"fields": fields}
            )
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Update failed: {response.text}"
                }
            
            return {
                "success": True,
                "contact_id": contact_id,
                "new_status": status
            }
    
    async def save_message_draft(
        self,
        contact_id: str,
        message_draft: str,
        table_name: str = "Contacts"
    ) -> dict:
        """
        Save a drafted message for a contact.
        Also updates status to "Drafted".
        """
        return await self.update_contact_status(
            contact_id,
            "Drafted",
            {"Message_Draft": message_draft},
            table_name
        )
    
    async def mark_contact_approved(
        self,
        contact_id: str,
        final_message: str,
        table_name: str = "Contacts"
    ) -> dict:
        """
        Mark a contact as approved with the final message.
        """
        return await self.update_contact_status(
            contact_id,
            "Approved",
            {"Message_Final": final_message},
            table_name
        )
    
    async def get_contact_with_job(
        self,
        contact_id: str,
        contacts_table: str = "Contacts",
        jobs_table: str = "Applications"  # Actual table name
    ) -> dict:
        """
        Get a contact with its linked job application data.
        This provides the full context needed for message generation.
        """
        # Get contact
        contact_url = f"{self.base_url}/{contacts_table}/{contact_id}"
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(contact_url, headers=self.headers)
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Contact not found: {response.text}"
                }
            
            contact_record = response.json()
            contact_fields = contact_record.get("fields", {})
            
            # Get linked job
            job_ids = contact_fields.get("Job_Application", [])
            job_data = {}
            
            if job_ids:
                job_id = job_ids[0]
                job_url = f"{self.base_url}/{jobs_table}/{job_id}"
                
                job_response = await client.get(job_url, headers=self.headers)
                if job_response.status_code == 200:
                    job_record = job_response.json()
                    job_fields = job_record.get("fields", {})
                    job_data = {
                        "job_id": job_record["id"],
                        "company": job_fields.get("Company", ""),
                        "role": job_fields.get("Job Position", ""),
                        "status": job_fields.get("Status", ""),
                        "job_description": job_fields.get("Full Description", ""),
                        "skill_audit": job_fields.get("Skill Audit", ""),
                        "resume_postgres_id": job_fields.get("Resume_Postgres_ID", None)
                    }
            
            return {
                "success": True,
                "contact": {
                    "contact_id": contact_record["id"],
                    "name": contact_fields.get("Name", ""),
                    "title": contact_fields.get("Title", ""),
                    "linkedin_url": contact_fields.get("LinkedIn_URL", ""),
                    "email": contact_fields.get("Email", ""),
                    "contact_type": contact_fields.get("Contact_Type", ""),
                    "contact_source": contact_fields.get("Contact_Source", "apollo"),
                    "connection_degree": contact_fields.get("Connection_Degree", "2nd"),
                    "connected_on": contact_fields.get("Connected_On", ""),
                    "message_draft": contact_fields.get("Message_Draft", "")
                },
                "job": job_data
            }
    
    # ==================== ACTIVE JOBS FOR FARMER PIPELINE ====================
    
    async def get_active_jobs_for_network_mining(
        self,
        table_name: str = "Applications"  # Actual table name
    ) -> dict:
        """
        Get all "In progress" jobs for the Farmer pipeline network overlap analysis.
        
        Returns simplified job list: company, role, status, job_id
        """
        filter_formula = '{Status} = "In progress"'  # lowercase 'p'
        
        url = f"{self.base_url}/{table_name}"
        params = {
            "filterByFormula": filter_formula,
            "fields[]": ["Company", "Job Position", "Status"],
            "pageSize": 100
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=self.headers, params=params)
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Airtable API error: {response.text}",
                    "jobs": []
                }
            
            records = response.json().get("records", [])
            
            jobs = []
            for record in records:
                fields = record.get("fields", {})
                jobs.append({
                    "job_id": record["id"],
                    "company": fields.get("Company", ""),
                    "role": fields.get("Job Position", ""),
                    "status": fields.get("Status", "")
                })
            
            return {
                "success": True,
                "total_jobs": len(jobs),
                "jobs": jobs
            }
