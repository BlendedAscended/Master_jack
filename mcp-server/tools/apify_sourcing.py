# mcp-server/tools/apify_sourcing.py
"""
Apify Contact Sourcing Tools (v2.0)

Replaces Apollo API with Apify actors for cost-effective contact discovery.

v2.0 Changes:
- LLM-powered hiring manager title extraction (DeepSeek)
- Airtable integration: fetch job data by job_id
- Scrapes location directly from job link
- Removed static title mapping in favor of intelligent LLM analysis

Features:
- Job link scraping for location extraction
- DeepSeek-powered hiring manager title generation
- Location-aware Google X-Ray search
- LinkedIn profile discovery with prioritization

Actors Used:
- apify/cheerio-scraper: Job posting parsing
- apify/google-search-scraper: LinkedIn X-Ray search
"""

import os
import re
import json
from typing import Optional
from openai import AsyncOpenAI
from apify_client import ApifyClientAsync


class ApifyTools:
    """
    Contact sourcing using Apify actors and DeepSeek LLM.
    
    Flow:
    1. Fetch job from Airtable (company, role, job_link)
    2. Scrape job_link for location
    3. Use DeepSeek to generate relevant hiring manager titles
    4. Google X-Ray search for LinkedIn profiles
    """
    
    def __init__(self):
        self.apify_token = os.environ.get("APIFY_API_TOKEN")
        if not self.apify_token:
            raise ValueError("APIFY_API_TOKEN environment variable not set")
        
        self.apify_client = ApifyClientAsync(token=self.apify_token)
        
        # DeepSeek client for LLM title extraction
        self.llm_client = AsyncOpenAI(
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com"
        )
        self.llm_model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    
    # ==================== LLM-POWERED TITLE EXTRACTION ====================
    
    async def _extract_hiring_manager_titles(
        self,
        job_position: str,
        job_description: str = "",
        company: str = "",
        location: str = ""
    ) -> dict:
        """
        Use DeepSeek to intelligently determine who would hire for this role.
        
        Much smarter than static mapping. Handles complex titles like:
        - "Health Data Analytics Consultant, Payment Model"
        - "Senior Revenue Cycle Business Analyst"
        - "Clinical Informaticist - Epic Beaker"
        
        Args:
            job_position: The exact job title from Airtable
            job_description: Full JD for context (optional but helps)
            company: Company name for industry context
            location: Location for regional/industry context
        
        Returns:
            dict with hiring_manager_titles, recruiter_titles, peer_titles
        """
        
        # Build context from JD if available
        jd_context = ""
        if job_description:
            # Extract first 1000 chars of JD for context
            jd_snippet = job_description[:1000]
            jd_context = f"\n\nJob Description Snippet:\n{jd_snippet}"
        
        system_prompt = """You are an expert at understanding organizational hierarchies and job roles.

Given a job position, company, and location, determine:
1. HIRING_MANAGER: Who would be the direct supervisor making the hiring decision? (1-2 levels above)
2. RECRUITER: What types of recruiters would handle this role?
3. PEERS: Who are similar-level colleagues at the same company?

Consider the COMPANY and LOCATION context:
- Different industries have different title conventions
- Healthcare companies often use titles like "CMIO", "Director of Clinical Informatics"
- Financial services may use "VP" more liberally
- Startups vs enterprises have different hierarchies
- Regional differences in title conventions (e.g., NYC finance vs SF tech)

Be SPECIFIC to the job function and industry. Don't use generic titles.

Examples:
- "Software Engineer" at Google (Mountain View) -> "Engineering Manager", "Director of Engineering"
- "Health Data Analytics Consultant" at VNS Health (New York) -> "Director of Population Health Analytics", "VP of Clinical Analytics"
- "Revenue Cycle Business Analyst" at Epic (Madison, WI) -> "Revenue Cycle Manager", "Director of Revenue Cycle"
- "Clinical Informaticist - Epic" at Mayo Clinic -> "CMIO", "Director of Clinical Informatics", "Epic Program Director"

Return ONLY valid JSON in this exact format:
{
  "hiring_manager_titles": ["Title 1", "Title 2", "Title 3"],
  "recruiter_titles": ["Recruiter Type 1", "Recruiter Type 2"],
  "peer_titles": ["Peer Title 1", "Peer Title 2"]
}"""

        user_prompt = f"""Job Position: {job_position}
Company: {company or "Unknown"}
Location: {location or "Unknown"}{jd_context}

What job titles should I search for on LinkedIn to find:
1. The hiring manager (decision maker, 1-2 levels above)
2. Recruiters who handle this type of role
3. Peers at similar level

Return ONLY the JSON object, no explanation."""

        try:
            response = await self.llm_client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,  # Low temp for consistent structured output
                max_tokens=500
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse JSON from response
            # Handle potential markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            result = json.loads(content)
            
            return {
                "success": True,
                "hiring_manager_titles": result.get("hiring_manager_titles", [])[:5],
                "recruiter_titles": result.get("recruiter_titles", [])[:3],
                "peer_titles": result.get("peer_titles", [])[:3],
                "source": "deepseek_llm"
            }
            
        except Exception as e:
            # Fallback to basic extraction
            return {
                "success": False,
                "error": str(e),
                "hiring_manager_titles": self._fallback_title_extraction(job_position),
                "recruiter_titles": ["Technical Recruiter", "Talent Acquisition", "Recruiter"],
                "peer_titles": [job_position],
                "source": "fallback"
            }
    
    def _fallback_title_extraction(self, job_position: str) -> list[str]:
        """Simple fallback if LLM fails - extract core function and add prefixes."""
        role_lower = job_position.lower()
        
        # Remove common prefixes/suffixes
        prefixes = ['senior ', 'junior ', 'lead ', 'staff ', 'principal ', 'associate ', 'intern ']
        core = role_lower
        for prefix in prefixes:
            core = core.replace(prefix, '')
        
        # Extract key function words
        function_words = []
        keywords = ['analyst', 'engineer', 'developer', 'manager', 'consultant', 'specialist', 
                   'coordinator', 'director', 'architect', 'designer', 'scientist', 'informaticist']
        
        for kw in keywords:
            if kw in core:
                function_words.append(kw)
        
        if function_words:
            base = function_words[0].title()
            return [
                f"Director of {base}s",
                f"Head of {base}s",
                f"VP of {base}s",
                f"{base} Manager"
            ]
        
        # Ultimate fallback
        core_title = core.split(',')[0].strip().title()
        return [
            f"Director of {core_title}",
            f"Head of {core_title}",
            "Hiring Manager"
        ]
    
    # ==================== JOB LINK SCRAPING ====================
    
    async def scrape_job_location(self, job_url: str) -> dict:
        """
        Scrape a job posting URL to extract location.
        
        This is the PRIMARY way to get location - from the actual job link.
        
        Args:
            job_url: The URL of the job posting
            
        Returns:
            dict with location, company (bonus), job_title (bonus), success status
        """
        if not job_url:
            return {"success": False, "error": "No job URL provided", "location": ""}
        
        parse_config = self._get_parse_config(job_url)
        
        run_input = {
            "startUrls": [{"url": job_url}],
            "pageFunction": parse_config["pageFunction"],
            "proxyConfiguration": {"useApifyProxy": True},
            "maxConcurrency": 1,
            "maxRequestsPerCrawl": 1
        }
        
        try:
            actor_client = self.apify_client.actor("apify/cheerio-scraper")
            run = await actor_client.call(run_input=run_input, timeout_secs=60)
            
            dataset_client = self.apify_client.dataset(run["defaultDatasetId"])
            items = []
            async for item in dataset_client.iterate_items():
                items.append(item)
            
            if items and items[0].get("success"):
                location = items[0].get("location", "")
                return {
                    "success": True,
                    "location": self._normalize_location(location),
                    "company": items[0].get("company", ""),
                    "job_title": items[0].get("job_title", ""),
                    "raw_location": location,
                    "source": "apify_scraper"
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to extract location",
                    "location": "",
                    "company": "",
                    "job_title": ""
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Scraping failed: {str(e)}",
                "location": "",
                "company": "",
                "job_title": ""
            }
    
    def _get_parse_config(self, job_url: str) -> dict:
        """Get parsing configuration based on job board URL."""
        url_lower = job_url.lower()
        
        # LinkedIn jobs
        if "linkedin.com" in url_lower:
            return {
                "pageFunction": """
                async function pageFunction(context) {
                    const { $, request } = context;
                    
                    const company = $('a.topcard__org-name-link').text().trim() ||
                                   $('.top-card-layout__card h4 a').text().trim() ||
                                   $('[data-tracking-control-name="public_jobs_topcard-org-name"]').text().trim();
                    
                    const location = $('.topcard__flavor--bullet').first().text().trim() ||
                                    $('.top-card-layout__card .topcard__flavor').eq(1).text().trim() ||
                                    $('[class*="job-details-jobs-unified-top-card__bullet"]').first().text().trim();
                    
                    const job_title = $('h1.topcard__title').text().trim() ||
                                     $('.top-card-layout__card h1').text().trim() ||
                                     $('h1').first().text().trim();
                    
                    return {
                        success: !!(company || location),
                        company: company || '',
                        location: location || '',
                        job_title: job_title || '',
                        url: request.url
                    };
                }
                """
            }
        
        # Greenhouse
        if "greenhouse.io" in url_lower or "boards.greenhouse.io" in url_lower:
            return {
                "pageFunction": """
                async function pageFunction(context) {
                    const { $, request } = context;
                    
                    const company = $('span.company-name').text().trim() ||
                                   $('.app-title').text().trim();
                    
                    const location = $('div.location').text().trim() ||
                                    $('.location').text().trim();
                    
                    const job_title = $('h1.app-title').text().trim() ||
                                     $('h1').first().text().trim();
                    
                    return {
                        success: !!(company || location),
                        company: company || '',
                        location: location || '',
                        job_title: job_title || '',
                        url: request.url
                    };
                }
                """
            }
        
        # Lever
        if "lever.co" in url_lower or "jobs.lever.co" in url_lower:
            return {
                "pageFunction": """
                async function pageFunction(context) {
                    const { $, request } = context;
                    
                    const company = $('a.main-header-logo img').attr('alt') ||
                                   $('title').text().split(' - ')[1] || '';
                    
                    const location = $('div.location').text().trim() ||
                                    $('.posting-categories .location').text().trim();
                    
                    const job_title = $('h2[data-qa="posting-name"]').text().trim() ||
                                     $('h2').first().text().trim();
                    
                    return {
                        success: !!(company || location),
                        company: company.trim(),
                        location: location || '',
                        job_title: job_title || '',
                        url: request.url
                    };
                }
                """
            }
        
        # Generic fallback
        return {
            "pageFunction": """
            async function pageFunction(context) {
                const { $, request } = context;
                
                const company = $('[class*="company"]').first().text().trim() ||
                               $('[data-company]').text().trim() ||
                               $('meta[property="og:site_name"]').attr('content') || '';
                
                const location = $('[class*="location"]').first().text().trim() ||
                                $('[data-location]').text().trim() ||
                                $('address').first().text().trim() || '';
                
                const job_title = $('h1').first().text().trim() ||
                                 $('title').text().split(' - ')[0].trim() || '';
                
                return {
                    success: !!(company || location),
                    company: company,
                    location: location,
                    job_title: job_title,
                    url: request.url
                };
            }
            """
        }
    
    # ==================== LOCATION PROCESSING ====================
    
    def _should_include_location(self, location: str) -> bool:
        """Determine if location should be included in search query."""
        if not location:
            return False
        
        location_lower = location.lower().strip()
        
        # Generic locations to exclude
        generic_patterns = [
            "remote", "united states", "usa", "us", "anywhere",
            "global", "worldwide", "work from home", "wfh", "hybrid", "flexible"
        ]
        
        for pattern in generic_patterns:
            if pattern in location_lower:
                return False
        
        # Exclude country-only locations
        country_only = [
            "canada", "uk", "united kingdom", "germany", "france",
            "australia", "india", "brazil", "mexico", "japan"
        ]
        
        if location_lower.strip() in country_only:
            return False
        
        return True
    
    def _normalize_location(self, location: str) -> str:
        """Normalize location string for search query."""
        if not location:
            return ""
        
        location = re.sub(r'\s*\(.*?\)\s*', '', location)
        location = re.sub(r',\s*(usa|us|united states).*$', '', location, flags=re.IGNORECASE)
        
        parts = [p.strip() for p in location.split(',')]
        if len(parts) >= 2:
            return ', '.join(parts[:2])
        
        return location.strip()
    
    # ==================== GOOGLE X-RAY SEARCH ====================
    
    async def _xray_search(
        self,
        company: str,
        titles: list[str],
        location: Optional[str],
        limit: int
    ) -> list[dict]:
        """Execute Google X-Ray search for LinkedIn profiles."""
        if not titles:
            return []
        
        # Build the title OR clause
        title_query = ' OR '.join([f'"{t}"' for t in titles[:5]])
        
        # Build the full query
        query_parts = [
            'site:linkedin.com/in/',
            f'"{company}"'
        ]
        
        if location and self._should_include_location(location):
            normalized = self._normalize_location(location)
            if normalized:
                query_parts.append(f'"{normalized}"')
        
        query_parts.append(f'({title_query})')
        query = ' '.join(query_parts)
        
        run_input = {
            "queries": query,
            "maxResults": limit * 2,
            "resultsPerPage": 10,
            "mobileResults": False,
            "languageCode": "en",
            "countryCode": "us",
            "saveHtml": False,
            "saveHtmlToKeyValueStore": False
        }
        
        try:
            actor_client = self.apify_client.actor("apify/google-search-scraper")
            run = await actor_client.call(run_input=run_input, timeout_secs=120)
            
            dataset_client = self.apify_client.dataset(run["defaultDatasetId"])
            results = []
            async for item in dataset_client.iterate_items():
                organic = item.get("organicResults", [])
                results.extend(organic)
            
            return results[:limit]
            
        except Exception as e:
            print(f"X-Ray search error: {str(e)}")
            return []
    
    def _parse_search_result(
        self,
        result: dict,
        contact_type: str,
        priority: int,
        scraped_location: str
    ) -> Optional[dict]:
        """Parse a Google search result into contact schema."""
        url = result.get("url", "")
        title = result.get("title", "")
        snippet = result.get("description", "")
        
        if "linkedin.com/in/" not in url.lower():
            return None
        
        clean_url = self._clean_linkedin_url(url)
        if not clean_url:
            return None
        
        name, job_title = self._parse_linkedin_title(title)
        if not name:
            return None
        
        # Check location match
        location_match = False
        if scraped_location:
            location_lower = scraped_location.lower()
            snippet_lower = (snippet + " " + title).lower()
            location_match = any(
                loc_part.lower() in snippet_lower 
                for loc_part in scraped_location.split(',')
            )
        
        return {
            "name": name,
            "title": job_title,
            "linkedin_url": clean_url,
            "email": None,
            "contact_type": contact_type,
            "contact_source": "apify_xray",
            "connection_degree": "2nd",
            "priority": priority,
            "location_match": location_match
        }
    
    def _clean_linkedin_url(self, url: str) -> Optional[str]:
        """Clean and normalize a LinkedIn profile URL."""
        if not url or "linkedin.com/in/" not in url.lower():
            return None
        
        match = re.search(r'linkedin\.com/in/([a-zA-Z0-9\-_]+)', url, re.IGNORECASE)
        if match:
            username = match.group(1)
            return f"https://www.linkedin.com/in/{username}/"
        return None
    
    def _parse_linkedin_title(self, title: str) -> tuple[str, str]:
        """Parse name and job title from LinkedIn search result title."""
        if not title:
            return ("", "")
        
        title = re.sub(r'\s*\|\s*LinkedIn\s*$', '', title, flags=re.IGNORECASE)
        parts = [p.strip() for p in title.split(' - ')]
        
        if len(parts) >= 2:
            return (parts[0], parts[1])
        elif len(parts) == 1:
            return (parts[0], "")
        return ("", "")
    
    # ==================== MAIN ENTRY POINT ====================
    
    async def discover_contacts_for_job(
        self,
        job_id: str,
        airtable_client,
        limit: int = 5
    ) -> dict:
        """
        Full contact discovery pipeline from Airtable job_id.
        
        This is the PRIMARY entry point for contact discovery.
        
        Flow:
        1. Fetch job from Airtable (company, role, job_link, job_description)
        2. Scrape job_link for location
        3. Use DeepSeek to generate relevant hiring manager titles
        4. Google X-Ray search for LinkedIn profiles
        
        Args:
            job_id: Airtable record ID (e.g., "rec0AH6wTYAWOBEVx")
            airtable_client: AirtableTools instance
            limit: Max contacts per category
        
        Returns:
            dict with contacts and metadata
        """
        # Step 1: Fetch job from Airtable
        job_data = await airtable_client.get_job_details(job_id)
        
        if not job_data.get("success"):
            return {
                "success": False,
                "error": job_data.get("error", "Failed to fetch job from Airtable"),
                "contacts": []
            }
        
        company = job_data.get("company", "")
        job_position = job_data.get("role", "")
        job_link = job_data.get("linkedin_url", "")  # This is actually the job link
        job_description = job_data.get("job_description", "")
        
        if not company or not job_position:
            return {
                "success": False,
                "error": "Missing company or job position in Airtable",
                "contacts": []
            }
        
        # Step 2: Scrape location from job link
        location = ""
        scrape_result = {"success": False}
        if job_link:
            scrape_result = await self.scrape_job_location(job_link)
            location = scrape_result.get("location", "")
        
        # Step 3: Use DeepSeek to generate relevant titles (with location context)
        title_extraction = await self._extract_hiring_manager_titles(
            job_position=job_position,
            job_description=job_description,
            company=company,
            location=location
        )
        
        hiring_manager_titles = title_extraction.get("hiring_manager_titles", [])
        recruiter_titles = title_extraction.get("recruiter_titles", [])
        peer_titles = title_extraction.get("peer_titles", [])
        
        # Step 4: Google X-Ray search for each contact type
        all_contacts = []
        
        contact_searches = [
            ("hiring_manager", hiring_manager_titles, 1),
            ("recruiter", recruiter_titles, 2),
            ("peer", peer_titles, 3)
        ]
        
        for contact_type, titles, priority in contact_searches:
            if not titles:
                continue
            
            try:
                results = await self._xray_search(
                    company=company,
                    titles=titles,
                    location=location,
                    limit=limit
                )
                
                for result in results:
                    contact = self._parse_search_result(
                        result,
                        contact_type=contact_type,
                        priority=priority,
                        scraped_location=location
                    )
                    if contact:
                        all_contacts.append(contact)
                        
            except Exception as e:
                print(f"Warning: Search failed for {contact_type}: {str(e)}")
                continue
        
        # Deduplicate by LinkedIn URL
        seen_urls = set()
        unique_contacts = []
        for contact in all_contacts:
            url = contact.get("linkedin_url", "").lower()
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_contacts.append(contact)
        
        return {
            "success": True,
            "job_id": job_id,
            "company": company,
            "job_position": job_position,
            "location_scraped": location,
            "location_used_in_search": self._should_include_location(location),
            "title_extraction": {
                "source": title_extraction.get("source"),
                "hiring_manager_titles": hiring_manager_titles,
                "recruiter_titles": recruiter_titles,
                "peer_titles": peer_titles
            },
            "scrape_result": {
                "success": scrape_result.get("success", False),
                "job_link": job_link
            },
            "contacts": unique_contacts[:limit * 3],
            "total_found": len(unique_contacts)
        }
    
    async def find_contacts(
        self,
        company: str,
        job_position: str,
        job_description: str = "",
        location: Optional[str] = None,
        limit: int = 5
    ) -> dict:
        """
        Find contacts without Airtable integration.
        
        Use this if you already have the job data and just need to search.
        
        Args:
            company: Company name
            job_position: The exact job title (from Airtable's Job Position field)
            job_description: Full JD for better title extraction
            location: Location to filter by (optional)
            limit: Max contacts per category
        
        Returns:
            dict with contacts matching existing schema
        """
        # Use LLM to generate relevant titles (with location context)
        title_extraction = await self._extract_hiring_manager_titles(
            job_position=job_position,
            job_description=job_description,
            company=company,
            location=location or ""
        )
        
        hiring_manager_titles = title_extraction.get("hiring_manager_titles", [])
        recruiter_titles = title_extraction.get("recruiter_titles", [])
        peer_titles = title_extraction.get("peer_titles", [])
        
        all_contacts = []
        
        contact_searches = [
            ("hiring_manager", hiring_manager_titles, 1),
            ("recruiter", recruiter_titles, 2),
            ("peer", peer_titles, 3)
        ]
        
        for contact_type, titles, priority in contact_searches:
            if not titles:
                continue
            
            try:
                results = await self._xray_search(
                    company=company,
                    titles=titles,
                    location=location,
                    limit=limit
                )
                
                for result in results:
                    contact = self._parse_search_result(
                        result,
                        contact_type=contact_type,
                        priority=priority,
                        scraped_location=location or ""
                    )
                    if contact:
                        all_contacts.append(contact)
                        
            except Exception as e:
                print(f"Warning: Search failed for {contact_type}: {str(e)}")
                continue
        
        # Deduplicate
        seen_urls = set()
        unique_contacts = []
        for contact in all_contacts:
            url = contact.get("linkedin_url", "").lower()
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_contacts.append(contact)
        
        return {
            "success": True,
            "company": company,
            "job_position": job_position,
            "location_used": location if self._should_include_location(location) else None,
            "title_extraction": {
                "source": title_extraction.get("source"),
                "hiring_manager_titles": hiring_manager_titles,
                "recruiter_titles": recruiter_titles,
                "peer_titles": peer_titles
            },
            "contacts": unique_contacts[:limit * 3],
            "total_found": len(unique_contacts)
        }
