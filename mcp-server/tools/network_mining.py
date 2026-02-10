# mcp-server/tools/network_mining.py
"""
Network Mining Tools (v2.0) - "The Farmer" Pipeline

Analyzes LinkedIn Connections.csv (from official data export) to find
existing connections working at target companies.

This is the SAFE approach to network mining:
- No scraping of linkedin.com
- Uses official LinkedIn data export feature
- Zero ban risk

How to get the CSV:
1. Go to LinkedIn Settings -> Data Privacy -> Get a copy of your data
2. Select "Connections" 
3. Download and save to Google Drive ~/Titan_Ingest folder
4. n8n watches this folder and triggers this tool
"""

import io
from typing import Optional
from datetime import datetime

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False


class NetworkMiningTools:
    def __init__(self):
        if not PANDAS_AVAILABLE:
            raise ImportError("pandas is required for network mining. Run: pip install pandas")
    
    async def analyze_network_overlap(
        self,
        csv_content: str,
        active_jobs: list[dict],
        fuzzy_match: bool = True
    ) -> dict:
        """
        Cross-reference LinkedIn connections with active job applications.
        Finds "insiders" - people you already know at target companies.
        
        Args:
            csv_content: Raw text content of Connections.csv
            active_jobs: List of job dicts with 'company', 'role', 'status', 'job_id'
            fuzzy_match: Whether to use fuzzy company name matching
        
        Returns:
            dict with insiders list, each containing contact info and job match
        
        Expected CSV columns (LinkedIn format):
        - First Name
        - Last Name  
        - Email Address (may be empty)
        - Company
        - Position
        - Connected On
        """
        # Parse CSV
        df = pd.read_csv(io.StringIO(csv_content))
        
        # Normalize column names (LinkedIn sometimes changes these)
        column_mapping = {
            'First Name': 'first_name',
            'Last Name': 'last_name',
            'Email Address': 'email',
            'Company': 'company',
            'Position': 'position',
            'Connected On': 'connected_on'
        }
        df = df.rename(columns=column_mapping)
        
        # Ensure required columns exist
        required = ['first_name', 'last_name', 'company']
        for col in required:
            if col not in df.columns:
                return {
                    "success": False,
                    "error": f"Missing required column: {col}",
                    "insiders": []
                }
        
        # Clean company names
        df['company_clean'] = df['company'].fillna('').str.lower().str.strip()
        
        matches = []
        
        for job in active_jobs:
            # Only process "In Progress" jobs
            if job.get('status', '').lower() != 'in progress':
                continue
            
            target_company = job.get('company', '').lower().strip()
            if not target_company:
                continue
            
            # Find connections at this company
            if fuzzy_match:
                # Fuzzy: check if target is contained in company name or vice versa
                mask = (
                    df['company_clean'].str.contains(target_company, na=False, regex=False) |
                    df['company_clean'].apply(lambda x: target_company in x if x else False)
                )
                
                # Also try common variations
                variations = self._get_company_variations(target_company)
                for var in variations:
                    mask |= df['company_clean'].str.contains(var, na=False, regex=False)
            else:
                # Exact match
                mask = df['company_clean'] == target_company
            
            insiders = df[mask]
            
            for _, person in insiders.iterrows():
                matches.append({
                    "contact_name": f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
                    "contact_email": person.get('email', '') if pd.notna(person.get('email')) else None,
                    "contact_role": person.get('position', 'Unknown'),
                    "company": person.get('company', target_company),
                    "company_normalized": target_company,
                    "connected_on": self._parse_date(person.get('connected_on')),
                    "target_role": job.get('role', ''),
                    "job_status": job.get('status', ''),
                    "job_id": job.get('job_id', ''),
                    "connection_degree": "1st",
                    "contact_source": "csv_import",
                    "match_confidence": "high" if not fuzzy_match else "fuzzy"
                })
        
        # Deduplicate by contact name + company
        seen = set()
        unique_matches = []
        for m in matches:
            key = (m['contact_name'].lower(), m['company_normalized'])
            if key not in seen:
                seen.add(key)
                unique_matches.append(m)
        
        return {
            "success": True,
            "total_connections": len(df),
            "jobs_analyzed": len([j for j in active_jobs if j.get('status', '').lower() == 'in progress']),
            "insiders_found": len(unique_matches),
            "insiders": unique_matches
        }
    
    def _get_company_variations(self, company: str) -> list[str]:
        """
        Generate common variations of a company name for fuzzy matching.
        
        "Epic Systems" -> ["epic", "epic systems", "epicsystems"]
        "Mayo Clinic" -> ["mayo", "mayo clinic", "mayoclinic"]
        """
        variations = [company]
        
        # Remove common suffixes
        suffixes = [' inc', ' inc.', ' llc', ' corp', ' corporation', ' systems', ' health', ' healthcare']
        clean = company
        for suffix in suffixes:
            if clean.endswith(suffix):
                clean = clean[:-len(suffix)].strip()
                variations.append(clean)
        
        # Remove spaces
        no_spaces = company.replace(' ', '')
        if no_spaces != company:
            variations.append(no_spaces)
        
        # First word only (for "Epic Systems" -> "Epic")
        first_word = company.split()[0] if ' ' in company else None
        if first_word and len(first_word) > 3:
            variations.append(first_word)
        
        return list(set(variations))
    
    def _parse_date(self, date_str) -> str:
        """
        Parse LinkedIn date format to ISO string.
        LinkedIn format is typically: "15 May 2023" or "May 15, 2023"
        """
        if pd.isna(date_str) or not date_str:
            return "Unknown"
        
        date_str = str(date_str).strip()
        
        formats = [
            "%d %b %Y",      # "15 May 2023"
            "%b %d, %Y",     # "May 15, 2023"
            "%Y-%m-%d",      # "2023-05-15"
            "%m/%d/%Y",      # "05/15/2023"
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        
        return date_str  # Return as-is if parsing fails
    
    async def get_network_stats(self, csv_content: str) -> dict:
        """
        Get general statistics about your LinkedIn network.
        Useful for understanding network composition.
        
        Returns:
            dict with total connections, top companies, oldest/newest connections
        """
        df = pd.read_csv(io.StringIO(csv_content))
        
        # Normalize columns
        column_mapping = {
            'First Name': 'first_name',
            'Last Name': 'last_name',
            'Company': 'company',
            'Position': 'position',
            'Connected On': 'connected_on'
        }
        df = df.rename(columns=column_mapping)
        
        # Top companies
        top_companies = df['company'].value_counts().head(10).to_dict()
        
        # Parse dates for oldest/newest
        dates = df['connected_on'].apply(self._parse_date)
        valid_dates = [d for d in dates if d != "Unknown"]
        
        return {
            "success": True,
            "total_connections": len(df),
            "top_companies": top_companies,
            "connections_with_email": df['email'].notna().sum() if 'email' in df.columns else 0,
            "oldest_connection": min(valid_dates) if valid_dates else "Unknown",
            "newest_connection": max(valid_dates) if valid_dates else "Unknown"
        }
    
    async def find_by_company(
        self,
        csv_content: str,
        company_name: str
    ) -> dict:
        """
        Find all connections at a specific company.
        
        Args:
            csv_content: Raw CSV content
            company_name: Company to search for
        
        Returns:
            dict with list of connections at that company
        """
        df = pd.read_csv(io.StringIO(csv_content))
        
        column_mapping = {
            'First Name': 'first_name',
            'Last Name': 'last_name',
            'Email Address': 'email',
            'Company': 'company',
            'Position': 'position',
            'Connected On': 'connected_on'
        }
        df = df.rename(columns=column_mapping)
        
        company_lower = company_name.lower()
        variations = self._get_company_variations(company_lower)
        
        mask = df['company'].fillna('').str.lower().apply(
            lambda x: any(var in x for var in variations)
        )
        
        connections = df[mask]
        
        result = []
        for _, person in connections.iterrows():
            result.append({
                "name": f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
                "role": person.get('position', 'Unknown'),
                "company": person.get('company', ''),
                "email": person.get('email') if pd.notna(person.get('email')) else None,
                "connected_on": self._parse_date(person.get('connected_on'))
            })
        
        return {
            "success": True,
            "company_searched": company_name,
            "connections_found": len(result),
            "connections": result
        }
