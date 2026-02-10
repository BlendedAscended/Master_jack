# mcp-server/tools/apollo.py
"""
Apollo.io Contact Discovery Tools

Finds hiring managers, recruiters, and team members at target companies.
Free tier: 200 searches/day

NOTE: Apollo provides 2nd/3rd degree contacts (strangers).
For 1st degree (existing connections), use network_mining.py with CSV export.
"""

import os
from typing import Optional
import httpx


class ApolloTools:
    def __init__(self):
        self.api_key = os.environ.get("APOLLO_API_KEY")
        self.base_url = "https://api.apollo.io/v1"
        
        if not self.api_key:
            raise ValueError("APOLLO_API_KEY environment variable not set")
    
    def _get_role_titles(self, job_title: str) -> dict:
        """
        Determine relevant contact titles based on the job role.
        Returns dict with managers, peers, recruiters lists.
        """
        title = job_title.lower()
        
        # Engineering / Technical roles
        if any(x in title for x in ['engineer', 'developer', 'swe', 'software', 'backend', 'frontend', 'fullstack', 'devops', 'sre']):
            return {
                'managers': ['Engineering Manager', 'Director of Engineering', 'VP Engineering', 'Tech Lead', 'Head of Engineering', 'CTO', 'Senior Engineering Manager'],
                'peers': ['Senior Engineer', 'Staff Engineer', 'Principal Engineer', 'Senior Developer', 'Lead Engineer', 'Senior Software Engineer'],
                'recruiters': ['Technical Recruiter', 'Engineering Recruiter', 'Talent Acquisition', 'Tech Recruiter']
            }
        
        # Product Management
        if any(x in title for x in ['product manager', 'product owner', 'pm', 'product']):
            return {
                'managers': ['Director of Product', 'VP Product', 'Group Product Manager', 'Head of Product', 'CPO', 'Senior Director Product'],
                'peers': ['Senior Product Manager', 'Staff PM', 'Principal PM', 'Lead Product Manager', 'Product Lead'],
                'recruiters': ['Product Recruiter', 'Technical Recruiter', 'Talent Acquisition']
            }
        
        # Data / Analytics / ML roles
        if any(x in title for x in ['data', 'analyst', 'analytics', 'ml', 'machine learning', 'ai', 'bi', 'business intelligence']):
            return {
                'managers': ['Data Science Manager', 'Director of Analytics', 'Head of Data', 'VP Data', 'Chief Data Officer', 'Analytics Manager', 'Director of Data Engineering'],
                'peers': ['Senior Data Scientist', 'Staff Analyst', 'Lead Data Engineer', 'ML Engineer', 'Principal Data Scientist', 'Senior Data Analyst', 'Senior BI Developer'],
                'recruiters': ['Data Recruiter', 'Technical Recruiter', 'Analytics Recruiter']
            }
        
        # Design roles
        if any(x in title for x in ['design', 'ux', 'ui', 'product design']):
            return {
                'managers': ['Design Director', 'Head of Design', 'VP Design', 'Design Manager', 'Creative Director'],
                'peers': ['Senior Designer', 'Staff Designer', 'Principal Designer', 'Lead Designer', 'Senior UX Designer'],
                'recruiters': ['Design Recruiter', 'Creative Recruiter', 'UX Recruiter']
            }
        
        # Healthcare specific
        if any(x in title for x in ['healthcare', 'health', 'clinical', 'medical', 'epic', 'ehr', 'emr']):
            return {
                'managers': ['Director of Health IT', 'VP Clinical Informatics', 'Health IT Manager', 'Director of Analytics', 'CMIO'],
                'peers': ['Senior Health Data Analyst', 'Clinical Data Analyst', 'Health Informaticist', 'Senior BI Developer'],
                'recruiters': ['Healthcare Recruiter', 'Health IT Recruiter', 'Technical Recruiter']
            }
        
        # Default for unknown roles
        return {
            'managers': ['Hiring Manager', 'Director', 'VP', 'Head of', 'Manager', 'Team Lead'],
            'peers': ['Senior', 'Lead', 'Staff', 'Principal'],
            'recruiters': ['Recruiter', 'Talent Acquisition', 'HR', 'People Operations']
        }
    
    async def find_contacts(
        self,
        company_name: str,
        job_title: str,
        limit: int = 5
    ) -> dict:
        """
        Find relevant contacts at a company based on job role.
        
        Returns prioritized list:
        - Priority 1: Hiring managers
        - Priority 2: Recruiters  
        - Priority 3: Team members/peers
        
        Args:
            company_name: Target company name
            job_title: Role you're applying for
            limit: Max contacts to return (default 5)
        
        Returns:
            dict with contacts list sorted by priority
        """
        titles = self._get_role_titles(job_title)
        all_contacts = []
        
        async with httpx.AsyncClient(timeout=30) as client:
            # Search each category
            for contact_type, priority, title_list in [
                ('hiring_manager', 1, titles['managers']),
                ('recruiter', 2, titles['recruiters']),
                ('team_member', 3, titles['peers'])
            ]:
                try:
                    response = await client.post(
                        f"{self.base_url}/mixed_people/search",
                        headers={
                            "X-Api-Key": self.api_key,
                            "Content-Type": "application/json"
                        },
                        json={
                            "organization_names": [company_name],
                            "person_titles": title_list,
                            "page": 1,
                            "per_page": 3  # Get 3 per category
                        }
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        for person in data.get("people", []):
                            all_contacts.append({
                                "name": person.get("name", ""),
                                "title": person.get("title", ""),
                                "linkedin_url": person.get("linkedin_url", ""),
                                "email": person.get("email"),
                                "contact_type": contact_type,
                                "contact_source": "apollo",
                                "connection_degree": "2nd",  # Apollo returns non-connections
                                "priority": priority,
                                "company": company_name
                            })
                    else:
                        # Log but don't fail
                        print(f"Apollo search warning for {contact_type}: {response.status_code}")
                        
                except Exception as e:
                    print(f"Apollo search error for {contact_type}: {e}")
        
        # Deduplicate by LinkedIn URL
        seen = set()
        unique_contacts = []
        for c in all_contacts:
            url = c.get("linkedin_url")
            if url and url not in seen:
                seen.add(url)
                unique_contacts.append(c)
            elif not url:
                # Keep contacts without URL but dedupe by name
                name_key = c.get("name", "").lower()
                if name_key and name_key not in seen:
                    seen.add(name_key)
                    unique_contacts.append(c)
        
        # Sort by priority
        unique_contacts.sort(key=lambda x: x["priority"])
        
        return {
            "success": True,
            "company": company_name,
            "job_title": job_title,
            "contacts": unique_contacts[:limit],
            "total_found": len(unique_contacts),
            "note": "Contacts are 2nd/3rd degree (strangers). Use Hunter pipeline."
        }
    
    async def search_people(
        self,
        company_name: str,
        person_titles: list[str],
        limit: int = 5
    ) -> dict:
        """
        Direct people search with specific titles.
        Use when you need more control over who to find.
        
        Args:
            company_name: Target company
            person_titles: List of job titles to search for
            limit: Max results
        """
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/mixed_people/search",
                    headers={
                        "X-Api-Key": self.api_key,
                        "Content-Type": "application/json"
                    },
                    json={
                        "organization_names": [company_name],
                        "person_titles": person_titles,
                        "page": 1,
                        "per_page": limit
                    }
                )
                
                if response.status_code == 200:
                    people = response.json().get("people", [])
                    return {
                        "success": True,
                        "contacts": [{
                            "name": p.get("name", ""),
                            "title": p.get("title", ""),
                            "linkedin_url": p.get("linkedin_url", ""),
                            "email": p.get("email"),
                            "contact_source": "apollo",
                            "connection_degree": "2nd"
                        } for p in people]
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Apollo API error: {response.status_code} - {response.text}",
                        "contacts": []
                    }
                    
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "contacts": []
                }
    
    async def get_usage_stats(self) -> dict:
        """
        Check Apollo API usage/credits remaining.
        Free tier: 200 credits/day
        """
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/credits",
                    headers={"X-Api-Key": self.api_key}
                )
                
                if response.status_code == 200:
                    return {
                        "success": True,
                        "credits": response.json()
                    }
                else:
                    return {
                        "success": False,
                        "error": "Could not fetch usage stats"
                    }
            except Exception as e:
                return {"success": False, "error": str(e)}
