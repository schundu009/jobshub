"""
Job ingestion service for fetching jobs from ATS platforms.
Supports: Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Recruitee, Workday

Security: Uses proper SSL verification by default.
Set DISABLE_SSL_VERIFY=true in development only if needed.
"""
import re
import urllib.request
import urllib.error
import json
import ssl
import os
import logging
from typing import Optional, Tuple
from datetime import date

logger = logging.getLogger(__name__)

# Create SSL context with proper certificate verification
# Only disable in development with explicit environment variable
DISABLE_SSL_VERIFY = os.getenv("DISABLE_SSL_VERIFY", "false").lower() == "true"

if DISABLE_SSL_VERIFY:
    logger.warning("SSL certificate verification is DISABLED. This should only be used in development!")
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
else:
    # Use default SSL context with certificate verification
    ssl_context = ssl.create_default_context()
    # Optionally use certifi if available for better CA bundle
    try:
        import certifi
        ssl_context.load_verify_locations(certifi.where())
    except ImportError:
        pass  # Use system CA bundle

# Supported ATS platforms with their public JSON APIs
SUPPORTED_ATS = {
    'greenhouse': 'Greenhouse',
    'lever': 'Lever',
    'ashby': 'Ashby',
    'smartrecruiters': 'SmartRecruiters',
    'workable': 'Workable',
    'recruitee': 'Recruitee',
    'workday': 'Workday',
    'apple': 'Apple',
    'intuit': 'Intuit',
    'adp': 'ADP',
    'eightfold': 'Eightfold',
}


def html_to_text(html: str) -> str:
    """
    Convert HTML to plain text while preserving structure.
    Keeps headings, paragraphs, and list formatting.
    """
    if not html:
        return ''

    text = html

    # Remove style, script, and head sections
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)

    # Replace headers with double newlines to create clear sections
    text = re.sub(r'<h[1-6][^>]*>(.*?)</h[1-6]>', r'\n\n\1\n\n', text, flags=re.IGNORECASE | re.DOTALL)

    # Replace <br> and <br/> with newlines
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)

    # Replace block-level closing tags with appropriate newlines
    text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</li>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</tr>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</td>', ' | ', text, flags=re.IGNORECASE)
    text = re.sub(r'</th>', ' | ', text, flags=re.IGNORECASE)

    # Add newline before block-level opening tags
    text = re.sub(r'<p[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<div[^>]*>', '\n', text, flags=re.IGNORECASE)

    # Replace <li> with bullet points
    text = re.sub(r'<li[^>]*>', '\n• ', text, flags=re.IGNORECASE)

    # Replace <ul> and <ol> with newlines
    text = re.sub(r'<[uo]l[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</[uo]l>', '\n', text, flags=re.IGNORECASE)

    # Handle strong/bold text - add slight spacing for readability
    text = re.sub(r'<strong[^>]*>(.*?)</strong>', r'\1', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<b[^>]*>(.*?)</b>', r'\1', text, flags=re.IGNORECASE | re.DOTALL)

    # Remove all remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Decode common HTML entities
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    text = text.replace('&#39;', "'")
    text = text.replace('&rsquo;', "'")
    text = text.replace('&lsquo;', "'")
    text = text.replace('&rdquo;', '"')
    text = text.replace('&ldquo;', '"')
    text = text.replace('&ndash;', '–')
    text = text.replace('&mdash;', '—')
    text = text.replace('&bull;', '•')
    text = text.replace('&#x27;', "'")
    text = text.replace('&apos;', "'")

    # Decode numeric HTML entities
    text = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), text)
    text = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: chr(int(m.group(1), 16)), text)

    # Clean up excessive whitespace while preserving paragraph breaks
    text = re.sub(r'[ \t]+', ' ', text)  # Multiple spaces/tabs to single space
    text = re.sub(r'\n ', '\n', text)  # Remove space after newline
    text = re.sub(r' \n', '\n', text)  # Remove space before newline
    text = re.sub(r'\n{3,}', '\n\n', text)  # Max 2 consecutive newlines

    return text.strip()


def _discover_workday_site(company: str, wd_number: str) -> Optional[str]:
    """
    Try to discover the Workday site name by probing common site names.
    Returns the site name if found, None otherwise.
    """
    # Common Workday site name patterns
    common_sites = [
        'External_Career_Site',
        f'{company.title()}ExternalCareerSite',
        f'{company.upper()}ExternalCareerSite',
        'Careers',
        'External',
        f'{company.title()}Careers',
        f'{company.upper()}Careers',
        f'{company.title()}_External_Career_Site',
        f'{company.upper()}_External_Career_Site',
        'en-US/External_Career_Site',
    ]

    base_url = f"https://{company}.{wd_number}.myworkdayjobs.com"

    for site in common_sites:
        api_url = f"{base_url}/wday/cxs/{company}/{site}/jobs"
        try:
            request_data = json.dumps({
                "appliedFacets": {},
                "limit": 1,
                "offset": 0,
                "searchText": ""
            }).encode('utf-8')

            request = urllib.request.Request(
                api_url,
                data=request_data,
                headers={
                    'User-Agent': 'JobTrails/1.0',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                method='POST'
            )
            with urllib.request.urlopen(request, timeout=10, context=ssl_context) as response:
                data = json.loads(response.read().decode('utf-8'))
                if data.get('jobPostings') is not None:
                    logger.info(f"Discovered Workday site for {company}: {site}")
                    return site
        except Exception:
            continue

    return None


def detect_ats_type(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Detect ATS type and company slug from a career page URL.

    Returns:
        Tuple of (ats_type, company_slug) or (None, None) if not detected.

    Supported URL patterns:
    - Greenhouse:
        - https://boards.greenhouse.io/{company}
        - https://job-boards.greenhouse.io/{company}
        - https://{company}.greenhouse.io
    - Lever:
        - https://jobs.lever.co/{company}
        - https://{company}.lever.co
    - Ashby:
        - https://jobs.ashbyhq.com/{company}
        - https://{company}.ashbyhq.com
    - SmartRecruiters:
        - https://jobs.smartrecruiters.com/{company}
        - https://careers.smartrecruiters.com/{company}
    - Workable:
        - https://apply.workable.com/{company}
        - https://{company}.workable.com
    - Recruitee:
        - https://{company}.recruitee.com
    - Workday:
        - https://{company}.wd{number}.myworkdayjobs.com/{site}
    """
    original_url = url.strip()  # Keep original for Workday (case-sensitive site names)
    url = original_url.lower()

    # Greenhouse patterns
    greenhouse_patterns = [
        r'boards\.greenhouse\.io/([a-z0-9_-]+)',
        r'job-boards\.greenhouse\.io/([a-z0-9_-]+)',
        r'([a-z0-9_-]+)\.greenhouse\.io',
    ]

    for pattern in greenhouse_patterns:
        match = re.search(pattern, url)
        if match:
            slug = match.group(1)
            if slug not in ['www', 'boards', 'job-boards', 'api']:
                return ('greenhouse', slug)

    # Lever patterns
    lever_patterns = [
        r'jobs\.lever\.co/([a-z0-9_-]+)',
        r'([a-z0-9_-]+)\.lever\.co',
    ]

    for pattern in lever_patterns:
        match = re.search(pattern, url)
        if match:
            slug = match.group(1)
            if slug not in ['www', 'jobs', 'api']:
                return ('lever', slug)

    # Ashby patterns
    ashby_patterns = [
        r'jobs\.ashbyhq\.com/([a-z0-9_-]+)',
        r'([a-z0-9_-]+)\.ashbyhq\.com',
    ]

    for pattern in ashby_patterns:
        match = re.search(pattern, url)
        if match:
            slug = match.group(1)
            if slug not in ['www', 'jobs', 'api']:
                return ('ashby', slug)

    # SmartRecruiters patterns
    smartrecruiters_patterns = [
        r'jobs\.smartrecruiters\.com/([a-z0-9_-]+)',
        r'careers\.smartrecruiters\.com/([a-z0-9_-]+)',
    ]

    for pattern in smartrecruiters_patterns:
        match = re.search(pattern, url)
        if match:
            slug = match.group(1)
            if slug not in ['www', 'jobs', 'api', 'careers']:
                return ('smartrecruiters', slug)

    # Workable patterns
    workable_patterns = [
        r'apply\.workable\.com/([a-z0-9_-]+)',
        r'([a-z0-9_-]+)\.workable\.com',
    ]

    for pattern in workable_patterns:
        match = re.search(pattern, url)
        if match:
            slug = match.group(1)
            if slug not in ['www', 'apply', 'api']:
                return ('workable', slug)

    # Recruitee patterns
    recruitee_patterns = [
        r'([a-z0-9_-]+)\.recruitee\.com',
    ]

    for pattern in recruitee_patterns:
        match = re.search(pattern, url)
        if match:
            slug = match.group(1)
            if slug not in ['www', 'api', 'app']:
                return ('recruitee', slug)

    # Workday patterns - URLs like: nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite
    # Also handle URLs without site name: salesforce.wd12.myworkdayjobs.com/
    # Note: Site name is case-sensitive in Workday API, so extract from original_url
    workday_pattern_full = r'([a-z0-9_-]+)\.wd(\d+)\.myworkdayjobs\.com/([a-zA-Z0-9_-]+)'
    match = re.search(workday_pattern_full, original_url, re.IGNORECASE)
    if match:
        company = match.group(1).lower()
        wd_number = match.group(2)
        site = match.group(3)  # Keep original case for site name
        # Store as company:wd_number:site
        return ('workday', f"{company}:wd{wd_number}:{site}")

    # Workday pattern without site name - try to discover it
    workday_pattern_base = r'([a-z0-9_-]+)\.wd(\d+)\.myworkdayjobs\.com/?$'
    match = re.search(workday_pattern_base, original_url, re.IGNORECASE)
    if match:
        company = match.group(1).lower()
        wd_number = match.group(2)
        # Try to discover the site name by probing the API
        site = _discover_workday_site(company, f"wd{wd_number}")
        if site:
            return ('workday', f"{company}:wd{wd_number}:{site}")

    # Apple Jobs - https://jobs.apple.com
    if 'jobs.apple.com' in url:
        return ('apple', 'apple')

    # Intuit Jobs - https://jobs.intuit.com
    if 'jobs.intuit.com' in url:
        return ('intuit', 'intuit')

    # ADP Workforce Now - https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html?cid=xxx
    if 'workforcenow.adp.com' in url:
        # Extract company ID from cid parameter
        cid_match = re.search(r'[?&]cid=([a-f0-9-]+)', url, re.IGNORECASE)
        if cid_match:
            return ('adp', cid_match.group(1))
        return ('adp', None)

    # Eightfold AI - Standard pattern: https://{company}.eightfold.ai/careers?domain={domain}
    # URL format: paypal.eightfold.ai/careers?domain=paypal.com
    eightfold_pattern = r'([a-z0-9_-]+)\.eightfold\.ai'
    match = re.search(eightfold_pattern, url)
    if match:
        company = match.group(1)
        if company not in ['www', 'api', 'app']:
            # Check for domain parameter which specifies the actual company domain
            domain_match = re.search(r'[?&]domain=([a-z0-9_.-]+)', url)
            if domain_match:
                # Use subdomain:domain format for slug (e.g., "paypal:paypal.com")
                domain = domain_match.group(1)
                return ('eightfold', f"{company}:{domain}")
            return ('eightfold', company)

    # Eightfold AI - Custom domains (Microsoft, etc.)
    # Known custom Eightfold domains
    custom_eightfold_domains = {
        'apply.careers.microsoft.com': ('apply.careers.microsoft.com', 'microsoft.com'),
        'jobs.careers.microsoft.com': ('jobs.careers.microsoft.com', 'microsoft.com'),
    }

    from urllib.parse import urlparse
    parsed = urlparse(url if url.startswith('http') else f'https://{url}')
    hostname = parsed.netloc.lower()

    if hostname in custom_eightfold_domains:
        base_domain, company_domain = custom_eightfold_domains[hostname]
        return ('eightfold', f"{base_domain}:{company_domain}")

    # Check for domain parameter with /careers path (potential Eightfold custom domain)
    if '/careers' in url:
        domain_match = re.search(r'[?&]domain=([a-z0-9_.-]+)', url)
        if domain_match:
            # Could be Eightfold - use hostname as base
            return ('eightfold', f"{hostname}:{domain_match.group(1)}")

    return (None, None)


def fetch_greenhouse_jobs(company_slug: str) -> list:
    """
    Fetch jobs from Greenhouse public API.
    API endpoint: https://boards-api.greenhouse.io/v1/boards/{company}/jobs
    """
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs?content=true"

    try:
        request = urllib.request.Request(
            api_url,
            headers={'User-Agent': 'JobTrails/1.0'}
        )
        with urllib.request.urlopen(request, timeout=30, context=ssl_context) as response:
            data = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"Company '{company_slug}' not found on Greenhouse")
        raise ValueError(f"Greenhouse API error: {e.code}")
    except urllib.error.URLError as e:
        raise ValueError(f"Network error: {str(e)}")
    except json.JSONDecodeError:
        raise ValueError("Invalid response from Greenhouse API")

    jobs = []
    for job_data in data.get('jobs', []):
        location = None
        if job_data.get('location'):
            location = job_data['location'].get('name', '')

        description = job_data.get('content', '')
        description = html_to_text(description)

        job_url = job_data.get('absolute_url', '')

        # Get department from departments array
        departments = job_data.get('departments', [])
        department = departments[0].get('name', '') if departments else None

        # Get posted date from updated_at
        posted_date = job_data.get('updated_at')

        normalized_job = {
            'title': job_data.get('title', 'Untitled'),
            'location': location,
            'job_url': job_url,
            'job_description': description,
            'source': 'greenhouse',
            'external_job_id': str(job_data.get('id', '')),
            'posted_date': posted_date,
            'department': department,
        }
        jobs.append(normalized_job)

    return jobs


def fetch_lever_jobs(company_slug: str) -> list:
    """
    Fetch jobs from Lever public API.
    API endpoint: https://api.lever.co/v0/postings/{company}
    """
    api_url = f"https://api.lever.co/v0/postings/{company_slug}"

    try:
        request = urllib.request.Request(
            api_url,
            headers={'User-Agent': 'JobTrails/1.0'}
        )
        with urllib.request.urlopen(request, timeout=30, context=ssl_context) as response:
            data = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"Company '{company_slug}' not found on Lever")
        raise ValueError(f"Lever API error: {e.code}")
    except urllib.error.URLError as e:
        raise ValueError(f"Network error: {str(e)}")
    except json.JSONDecodeError:
        raise ValueError("Invalid response from Lever API")

    jobs = []
    for job_data in data:
        location = None
        categories = job_data.get('categories', {})
        if categories.get('location'):
            location = categories['location']

        description = job_data.get('descriptionPlain', '')
        if not description:
            desc_parts = []
            for list_item in job_data.get('lists', []):
                list_text = list_item.get('text', '')
                list_content = list_item.get('content', '')
                if list_text:
                    desc_parts.append(f"\n{list_text}\n")
                if list_content:
                    desc_parts.append(html_to_text(list_content))
            description = '\n'.join(desc_parts).strip()

        job_url = job_data.get('hostedUrl', '')

        # Get posted date from createdAt (milliseconds timestamp)
        created_at = job_data.get('createdAt')
        posted_date = None
        if created_at:
            from datetime import datetime
            posted_date = datetime.fromtimestamp(created_at / 1000).isoformat()

        # Get department from categories.team
        department = categories.get('team')

        normalized_job = {
            'title': job_data.get('text', 'Untitled'),
            'location': location,
            'job_url': job_url,
            'job_description': description,
            'source': 'lever',
            'external_job_id': job_data.get('id', ''),
            'posted_date': posted_date,
            'department': department,
        }
        jobs.append(normalized_job)

    return jobs


def fetch_ashby_jobs(company_slug: str) -> list:
    """
    Fetch jobs from Ashby public API.
    API endpoint: https://api.ashbyhq.com/posting-api/job-board/{company}
    """
    api_url = f"https://api.ashbyhq.com/posting-api/job-board/{company_slug}"

    try:
        request = urllib.request.Request(
            api_url,
            headers={'User-Agent': 'JobTrails/1.0'}
        )
        with urllib.request.urlopen(request, timeout=30, context=ssl_context) as response:
            data = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"Company '{company_slug}' not found on Ashby")
        raise ValueError(f"Ashby API error: {e.code}")
    except urllib.error.URLError as e:
        raise ValueError(f"Network error: {str(e)}")
    except json.JSONDecodeError:
        raise ValueError("Invalid response from Ashby API")

    jobs = []
    for job_data in data.get('jobs', []):
        location = job_data.get('location', '')
        if isinstance(location, dict):
            location = location.get('name', '')

        description = job_data.get('descriptionPlain', '') or job_data.get('description', '')
        if description:
            description = html_to_text(description)

        job_url = job_data.get('jobUrl', '') or f"https://jobs.ashbyhq.com/{company_slug}/{job_data.get('id', '')}"

        # Get posted date from publishedAt or updatedAt
        posted_date = job_data.get('publishedAt') or job_data.get('updatedAt')

        # Get department from department or team
        department = job_data.get('department') or job_data.get('team')
        if isinstance(department, dict):
            department = department.get('name', '')

        normalized_job = {
            'title': job_data.get('title', 'Untitled'),
            'location': location,
            'job_url': job_url,
            'job_description': description,
            'source': 'ashby',
            'external_job_id': str(job_data.get('id', '')),
            'posted_date': posted_date,
            'department': department,
        }
        jobs.append(normalized_job)

    return jobs


def fetch_smartrecruiters_jobs(company_slug: str) -> list:
    """
    Fetch jobs from SmartRecruiters public API.
    API endpoint: https://api.smartrecruiters.com/v1/companies/{company}/postings
    """
    api_url = f"https://api.smartrecruiters.com/v1/companies/{company_slug}/postings"

    try:
        request = urllib.request.Request(
            api_url,
            headers={'User-Agent': 'JobTrails/1.0'}
        )
        with urllib.request.urlopen(request, timeout=30, context=ssl_context) as response:
            data = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"Company '{company_slug}' not found on SmartRecruiters")
        raise ValueError(f"SmartRecruiters API error: {e.code}")
    except urllib.error.URLError as e:
        raise ValueError(f"Network error: {str(e)}")
    except json.JSONDecodeError:
        raise ValueError("Invalid response from SmartRecruiters API")

    jobs = []
    for job_data in data.get('content', []):
        location_data = job_data.get('location', {})
        location_parts = []
        if location_data.get('city'):
            location_parts.append(location_data['city'])
        if location_data.get('region'):
            location_parts.append(location_data['region'])
        if location_data.get('country'):
            location_parts.append(location_data['country'])
        location = ', '.join(location_parts) if location_parts else None

        # SmartRecruiters doesn't include full description in list, just use what we have
        description = job_data.get('customField', [])
        desc_text = ''
        for field in description:
            if field.get('fieldLabel') == 'Description':
                desc_text = field.get('valueField', '')
                break

        job_url = job_data.get('ref', '') or f"https://jobs.smartrecruiters.com/{company_slug}/{job_data.get('id', '')}"

        normalized_job = {
            'title': job_data.get('name', 'Untitled'),
            'location': location,
            'job_url': job_url,
            'job_description': desc_text,
            'source': 'smartrecruiters',
            'external_job_id': str(job_data.get('id', '')),
        }
        jobs.append(normalized_job)

    return jobs


def fetch_workable_jobs(company_slug: str) -> list:
    """
    Fetch jobs from Workable public API.
    API endpoint: https://apply.workable.com/api/v1/widget/accounts/{company}
    """
    api_url = f"https://apply.workable.com/api/v1/widget/accounts/{company_slug}"

    try:
        request = urllib.request.Request(
            api_url,
            headers={'User-Agent': 'JobTrails/1.0'}
        )
        with urllib.request.urlopen(request, timeout=30, context=ssl_context) as response:
            data = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"Company '{company_slug}' not found on Workable")
        raise ValueError(f"Workable API error: {e.code}")
    except urllib.error.URLError as e:
        raise ValueError(f"Network error: {str(e)}")
    except json.JSONDecodeError:
        raise ValueError("Invalid response from Workable API")

    jobs = []
    for job_data in data.get('jobs', []):
        location = job_data.get('location', '')
        if isinstance(location, dict):
            location = location.get('city', '') or location.get('name', '')

        description = job_data.get('description', '')
        if description:
            description = html_to_text(description)

        shortcode = job_data.get('shortcode', '')
        job_url = job_data.get('url', '') or f"https://apply.workable.com/{company_slug}/j/{shortcode}"

        normalized_job = {
            'title': job_data.get('title', 'Untitled'),
            'location': location,
            'job_url': job_url,
            'job_description': description,
            'source': 'workable',
            'external_job_id': shortcode or str(job_data.get('id', '')),
        }
        jobs.append(normalized_job)

    return jobs


def fetch_recruitee_jobs(company_slug: str) -> list:
    """
    Fetch jobs from Recruitee public API.
    API endpoint: https://{company}.recruitee.com/api/offers
    """
    api_url = f"https://{company_slug}.recruitee.com/api/offers"

    try:
        request = urllib.request.Request(
            api_url,
            headers={'User-Agent': 'JobTrails/1.0'}
        )
        with urllib.request.urlopen(request, timeout=30, context=ssl_context) as response:
            data = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"Company '{company_slug}' not found on Recruitee")
        raise ValueError(f"Recruitee API error: {e.code}")
    except urllib.error.URLError as e:
        raise ValueError(f"Network error: {str(e)}")
    except json.JSONDecodeError:
        raise ValueError("Invalid response from Recruitee API")

    jobs = []
    for job_data in data.get('offers', []):
        location = job_data.get('location', '') or job_data.get('city', '')

        description = job_data.get('description', '')
        if description:
            description = html_to_text(description)

        slug = job_data.get('slug', '')
        job_url = job_data.get('careers_url', '') or f"https://{company_slug}.recruitee.com/o/{slug}"

        normalized_job = {
            'title': job_data.get('title', 'Untitled'),
            'location': location,
            'job_url': job_url,
            'job_description': description,
            'source': 'recruitee',
            'external_job_id': str(job_data.get('id', '')),
        }
        jobs.append(normalized_job)

    return jobs


def fetch_workday_job_details(base_url: str, company: str, site: str, external_path: str) -> dict:
    """
    Fetch full job details from Workday for a single job.
    Returns the job details dict or empty dict on failure.
    """
    if not external_path:
        return {}

    # API endpoint for job details
    detail_url = f"{base_url}/wday/cxs/{company}/{site}{external_path}"

    try:
        request = urllib.request.Request(
            detail_url,
            headers={
                'User-Agent': 'JobTrails/1.0',
                'Accept': 'application/json'
            }
        )
        with urllib.request.urlopen(request, timeout=15, context=ssl_context) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception:
        # If we can't fetch details, return empty dict
        return {}


def fetch_workday_jobs(company_slug: str) -> list:
    """
    Fetch jobs from Workday public API.
    company_slug format: "company:wd_number:site" (e.g., "nvidia:wd5:NVIDIAExternalCareerSite")
    API endpoint: POST https://{company}.{wd}.myworkdayjobs.com/wday/cxs/{company}/{site}/jobs
    """
    parts = company_slug.split(':')
    if len(parts) != 3:
        raise ValueError(f"Invalid Workday slug format: {company_slug}. Expected 'company:wd#:site'")

    company, wd_number, site = parts
    base_url = f"https://{company}.{wd_number}.myworkdayjobs.com"
    api_url = f"{base_url}/wday/cxs/{company}/{site}/jobs"

    all_jobs = []
    offset = 0
    limit = 20  # Workday only accepts limit=20
    max_jobs = 2000  # Cap to prevent extremely long fetches

    while True:
        try:
            request_data = json.dumps({
                "appliedFacets": {},
                "limit": limit,
                "offset": offset,
                "searchText": ""
            }).encode('utf-8')

            request = urllib.request.Request(
                api_url,
                data=request_data,
                headers={
                    'User-Agent': 'JobTrails/1.0',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                method='POST'
            )
            with urllib.request.urlopen(request, timeout=30, context=ssl_context) as response:
                data = json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise ValueError(f"Company '{company}' with site '{site}' not found on Workday")
            raise ValueError(f"Workday API error: {e.code}")
        except urllib.error.URLError as e:
            raise ValueError(f"Network error: {str(e)}")
        except json.JSONDecodeError:
            raise ValueError("Invalid response from Workday API")

        job_postings = data.get('jobPostings', [])
        if not job_postings:
            break

        for job_data in job_postings:
            title = job_data.get('title', 'Untitled')

            # Extract location from bulletFields or locationsText
            location = None
            if job_data.get('locationsText'):
                location = job_data['locationsText']
            elif job_data.get('bulletFields'):
                location = ', '.join(job_data['bulletFields'])

            # Job URL - Workday needs the full path with site name
            external_path = job_data.get('externalPath', '')
            if external_path:
                # external_path is like /job/Location/Title_ID, we need /en-US/{site}/job/Location/Title_ID
                job_url = f"{base_url}/en-US/{site}{external_path}"
            else:
                job_url = ''

            # Job ID - prefer extracting from external_path as it's more reliable
            # external_path format: /job/Location/Title_JobReqID
            job_id = ''
            if external_path:
                path_parts = external_path.split('/')
                if path_parts:
                    last_part = path_parts[-1]  # e.g., "Sr-Infrastructure-Engineer---Storage_JR0277455"
                    if '_' in last_part:
                        # Extract the job requisition ID after the last underscore
                        job_id = last_part.split('_')[-1]  # e.g., "JR0277455"
                    else:
                        job_id = last_part

            # Fallback to bulletFields if no ID extracted (but skip generic values like "Spotlight Job")
            if not job_id:
                bullet_fields = job_data.get('bulletFields', [])
                if bullet_fields and bullet_fields[0] and 'spotlight' not in bullet_fields[0].lower():
                    job_id = bullet_fields[0]
                else:
                    job_id = f"workday_{offset}"

            # Fetch full job details to get description
            job_description = ''
            posted_date = job_data.get('postedOn')
            department = None

            if external_path:
                details = fetch_workday_job_details(base_url, company, site, external_path)
                if details:
                    job_info = details.get('jobPostingInfo', {})
                    # Get full description from details
                    desc_html = job_info.get('jobDescription', '')
                    if desc_html:
                        job_description = html_to_text(desc_html)
                    # Get posted date from details if not in list
                    if not posted_date:
                        posted_date = job_info.get('postedOn') or job_info.get('startDate')
                    # Get department/category
                    department = job_info.get('jobCategory')

            # Fallback to teaser if no full description
            if not job_description:
                job_description = job_data.get('descriptionTeaser', '')

            normalized_job = {
                'title': title,
                'location': location,
                'job_url': job_url,
                'job_description': job_description,
                'source': 'workday',
                'external_job_id': job_id,
                'posted_date': posted_date,
                'department': department,
            }
            all_jobs.append(normalized_job)

        # Check if there are more jobs or we've hit the cap
        # Note: Workday only returns 'total' on first request, so we rely on empty jobPostings to stop
        total = data.get('total', 0)
        if total > 0:
            total_jobs = total  # Save the total from first request
        offset += limit

        # Stop if no more jobs returned or we've hit our cap
        if len(job_postings) < limit or len(all_jobs) >= max_jobs:
            break

    return all_jobs


def fetch_apple_jobs(company_slug: str) -> list:
    """
    Fetch jobs from Apple's careers page.

    Apple uses their own custom job portal at jobs.apple.com.
    The job data is embedded in the initial HTML response.
    """
    all_jobs = []
    max_pages = 10  # Apple has ~4500 jobs, 20 per page

    for page in range(1, max_pages + 1):
        url = f"https://jobs.apple.com/en-us/search?location=united-states-USA&page={page}"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }

        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=30, context=ssl_context) as response:
                html = response.read().decode('utf-8')

                # Parse jobs from the embedded JSON data
                jobs = _parse_apple_jobs_from_html(html)
                if not jobs:
                    break

                all_jobs.extend(jobs)

                # Check total records to know when to stop
                total_match = re.search(r'"totalRecords":\s*(\d+)', html)
                if total_match:
                    total = int(total_match.group(1))
                    if len(all_jobs) >= total or len(all_jobs) >= 200:  # Limit to 200 jobs
                        break

        except Exception as e:
            print(f"Error fetching Apple jobs page {page}: {e}")
            break

    return all_jobs


def _parse_apple_jobs_from_html(html: str) -> list:
    """
    Parse job listings from Apple careers HTML.
    The job data is embedded in a script tag as JSON.
    """
    jobs = []

    # Find the hydration data script
    pattern = r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\("(.+?)"\);'
    match = re.search(pattern, html)

    if not match:
        return jobs

    try:
        # Unescape the JSON string (it's double-escaped)
        json_str = match.group(1)
        json_str = json_str.replace('\\"', '"')
        json_str = json_str.replace('\\\\', '\\')

        data = json.loads(json_str)

        # Navigate to search results
        loader_data = data.get('loaderData', {})
        for key, value in loader_data.items():
            if isinstance(value, dict) and 'searchResults' in value:
                for job in value['searchResults']:
                    normalized = _normalize_apple_job(job)
                    if normalized:
                        jobs.append(normalized)
                break

    except json.JSONDecodeError as e:
        print(f"Apple JSON parse error: {e}")

    return jobs


def _normalize_apple_job(job: dict) -> dict:
    """
    Normalize Apple job data to match JobTrails format.
    """
    locations = job.get('locations', [])
    location_str = ''
    if locations:
        loc = locations[0]
        parts = [loc.get('city', ''), loc.get('stateProvince', ''), loc.get('countryName', '')]
        location_str = ', '.join(p for p in parts if p)
        if not location_str:
            location_str = loc.get('name', 'United States')

    team = job.get('team', {})
    team_name = team.get('teamName', '') if isinstance(team, dict) else ''

    job_id = job.get('id', '')
    title = job.get('postingTitle', job.get('transformedPostingTitle', 'Unknown Position'))

    return {
        'title': title,
        'location': location_str,
        'department': team_name,
        'job_description': job.get('jobSummary', ''),
        'job_url': f"https://jobs.apple.com/en-us/details/{job_id}",
        'source': 'apple',
        'external_job_id': job_id,
        'posted_date': job.get('postingDate'),
    }


def fetch_intuit_jobs(company_slug: str) -> list:
    """
    Fetch jobs from Intuit's careers page (TalentBrew platform).
    Scrapes HTML since there's no public API.
    URL: https://jobs.intuit.com/search-jobs
    """
    all_jobs = []
    base_url = "https://jobs.intuit.com"
    max_pages = 15  # Intuit has ~700 jobs, 15 per page

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }

    for page in range(1, max_pages + 1):
        # Page 1 has no param, subsequent pages use &p=N
        if page == 1:
            url = f"{base_url}/search-jobs"
        else:
            url = f"{base_url}/search-jobs?p={page}"

        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=30, context=ssl_context) as response:
                html = response.read().decode('utf-8')

                # Parse jobs from HTML
                jobs = _parse_intuit_jobs_from_html(html, base_url)
                if not jobs:
                    break

                all_jobs.extend(jobs)

                # Check if we've hit limit
                if len(all_jobs) >= 300:  # Limit to 300 jobs
                    break

        except Exception as e:
            print(f"Error fetching Intuit jobs page {page}: {e}")
            break

    return all_jobs


def _parse_intuit_jobs_from_html(html: str, base_url: str) -> list:
    """
    Parse job listings from Intuit careers HTML.
    Job links follow pattern: /job/{city}/{title-slug}/27595/{job-id}
    Title is inside an <h2> tag within the <a> tag.
    """
    jobs = []
    seen_ids = set()

    # Pattern: <a href="/job/city/slug/27595/id">...<h2>Title</h2>...</a>
    job_pattern = r'<a[^>]*href="(/job/([^/]+)/[^/]+/27595/(\d+))"[^>]*>.*?<h2>([^<]+)</h2>.*?</a>'
    matches = re.findall(job_pattern, html, re.DOTALL | re.IGNORECASE)

    for match in matches:
        job_path, city_slug, job_id, title = match

        if job_id in seen_ids:
            continue
        seen_ids.add(job_id)

        # Convert city slug to readable format
        location = city_slug.replace('-', ' ').title()

        # Clean up title (decode HTML entities)
        title = title.strip()
        title = title.replace('&amp;', '&')
        title = title.replace('&#39;', "'")
        title = title.replace('&quot;', '"')

        jobs.append({
            'title': title,
            'location': location,
            'job_url': f"{base_url}{job_path}",
            'job_description': '',
            'source': 'intuit',
            'external_job_id': job_id,
        })

    return jobs


def fetch_adp_jobs(company_slug: str) -> list:
    """
    Fetch jobs from ADP Workforce Now.
    API endpoint: https://workforcenow.adp.com/mascsr/default/careercenter/public/events/staffing/v1/job-requisitions?cid={company_id}
    """
    if not company_slug:
        raise ValueError("ADP company ID (cid) is required")

    api_url = f"https://workforcenow.adp.com/mascsr/default/careercenter/public/events/staffing/v1/job-requisitions?cid={company_slug}"

    try:
        request = urllib.request.Request(
            api_url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Accept': 'application/json'
            }
        )
        with urllib.request.urlopen(request, timeout=30, context=ssl_context) as response:
            data = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"Company not found on ADP with ID '{company_slug}'")
        raise ValueError(f"ADP API error: {e.code}")
    except urllib.error.URLError as e:
        raise ValueError(f"Network error: {str(e)}")
    except json.JSONDecodeError:
        raise ValueError("Invalid response from ADP API")

    jobs = []
    for job_data in data.get('jobRequisitions', []):
        title = job_data.get('requisitionTitle', 'Untitled')

        # Extract location from requisitionLocations
        location = None
        locations = job_data.get('requisitionLocations', [])
        if locations:
            name_code = locations[0].get('nameCode', {})
            location = name_code.get('shortName', '')
            if not location:
                address = locations[0].get('address', {})
                city = address.get('cityName', '')
                state = address.get('countrySubdivisionLevel1', {}).get('codeValue', '')
                if city and state:
                    location = f"{city}, {state}"
                elif city:
                    location = city

        # Get posted date
        posted_date = job_data.get('postDate')

        # Get job ID
        item_id = job_data.get('itemID', '')
        external_job_id = item_id.split('_')[0] if '_' in item_id else item_id

        # Get external job ID from custom fields if available
        custom_fields = job_data.get('customFieldGroup', {})
        string_fields = custom_fields.get('stringFields', [])
        for field in string_fields:
            if field.get('nameCode', {}).get('codeValue') == 'ExternalJobID':
                external_job_id = field.get('stringValue', external_job_id)
                break

        # Build job URL
        job_url = f"https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html?cid={company_slug}&jobId={item_id}&lang=en_US"

        # Get work level (Full Time, Part Time, etc.)
        work_level = job_data.get('workLevelCode', {}).get('shortName', '')

        normalized_job = {
            'title': title,
            'location': location.strip() if location else None,
            'job_url': job_url,
            'job_description': work_level if work_level else '',
            'source': 'adp',
            'external_job_id': external_job_id,
            'posted_date': posted_date,
        }
        jobs.append(normalized_job)

    return jobs


def fetch_eightfold_jobs(company_slug: str) -> list:
    """
    Fetch jobs from Eightfold AI career sites by parsing the sitemap.

    Eightfold provides a public sitemap with all job URLs at:
    https://{company}.eightfold.ai/careers/sitemap.xml?domain={domain}

    Company slug format: "subdomain:domain" (e.g., "paypal:paypal.com")
    """
    if not company_slug:
        raise ValueError("Eightfold company slug is required")

    # Parse company slug (format: subdomain:domain or just subdomain)
    if ':' in company_slug:
        base_host, domain = company_slug.split(':', 1)
    else:
        base_host = company_slug
        domain = f"{company_slug}.com"

    # Determine the base URL - could be standard Eightfold or custom domain
    if '.' in base_host and not base_host.endswith('.eightfold.ai'):
        # Custom domain like apply.careers.microsoft.com
        base_url = f"https://{base_host}"
    else:
        # Standard Eightfold subdomain
        base_url = f"https://{base_host}.eightfold.ai"

    # Fetch the sitemap
    sitemap_url = f"{base_url}/careers/sitemap.xml?domain={domain}"

    try:
        request = urllib.request.Request(
            sitemap_url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Accept': 'application/xml, text/xml, */*'
            }
        )
        with urllib.request.urlopen(request, timeout=30, context=ssl_context) as response:
            sitemap_content = response.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"Eightfold sitemap not found for '{subdomain}'")
        raise ValueError(f"Eightfold API error: {e.code}")
    except urllib.error.URLError as e:
        raise ValueError(f"Network error: {str(e)}")

    jobs = []

    # Parse the sitemap XML to extract job URLs
    # Job URLs look like: https://paypal.eightfold.ai/careers/job/274908270787-director-corporate-development-san-jose-california-united-states-of-america?domain=paypal.com
    job_url_pattern = re.compile(
        r'<loc>(https://[^<]+/careers/job/(\d+)-([^?<]+)\?domain=[^<]+)</loc>(?:\s*<lastmod>([^<]+)</lastmod>)?',
        re.IGNORECASE
    )

    for match in job_url_pattern.finditer(sitemap_content):
        job_url = match.group(1)
        external_job_id = match.group(2)
        slug_parts = match.group(3)
        lastmod = match.group(4) if match.group(4) else None

        # Parse title and location from URL slug
        # Eightfold slugs end with location: title-city-state/region-country
        # Example: director-corporate-development-san-jose-california-united-states-of-america
        slug_text = slug_parts.replace('-', ' ')

        # Known city patterns that indicate start of location
        city_patterns = [
            r'\b(san jose|san francisco|new york|los angeles|austin|seattle|chicago|boston|denver|atlanta|dallas|phoenix|portland|miami|nashville)\b',
            r'\b(london|dublin|berlin|stockholm|amsterdam|paris|munich|zurich|singapore|tokyo|sydney|melbourne|toronto|vancouver)\b',
            r'\b(chennai|bangalore|hyderabad|mumbai|pune|gurgaon|noida|delhi|kolkata)\b',
            r'\b(dreilinden)\b',  # PayPal specific locations
        ]

        # Country/region patterns that indicate location
        country_patterns = [
            r'\bunited states of america\b',
            r'\bunited states\b',
            r'\bunited kingdom\b',
            r'\b(india|germany|ireland|singapore|australia|england|sweden|china|japan|france|canada|netherlands|switzerland)\b$',
        ]

        # Try to find location start using city patterns
        location_start = None
        for pattern in city_patterns:
            match = re.search(pattern, slug_text.lower())
            if match:
                location_start = match.start()
                break

        # If no city found, try to find country at the end
        if location_start is None:
            for pattern in country_patterns:
                match = re.search(pattern, slug_text.lower())
                if match:
                    # Location is just the country/region portion
                    location_start = match.start()
                    break

        # Split into title and location
        if location_start and location_start > 5:  # Ensure title has at least a few chars
            title = slug_text[:location_start].strip()
            location = slug_text[location_start:].strip()
        else:
            # Fallback: use whole slug as title
            title = slug_text
            location = None

        # Clean up title (title case, fix abbreviations)
        title = ' '.join(word.title() for word in title.split())
        title = title.replace(' Sr ', ' Senior ').replace('Sr ', 'Senior ')
        title = title.replace(' Swe ', ' SWE ').replace('Swe ', 'SWE ')
        title = title.replace(' Mts ', ' MTS ').replace('Mts ', 'MTS ')

        # Clean up location
        if location:
            location = ' '.join(word.title() for word in location.split())
            # Normalize common patterns
            location = location.replace('United States Of America', 'USA')
            location = location.replace('United Kingdom', 'UK')
            # Format as "City, State/Country"
            location = location.strip()

        # Clean up common abbreviations
        title = title.replace('Sr ', 'Senior ').replace('Sr. ', 'Senior ')
        title = title.replace('Mts ', 'MTS ').replace('Swe ', 'SWE ')

        # Truncate fields to fit database column limits
        title = title.strip()[:255] if title else ''
        location = location.strip()[:255] if location else None
        job_url = job_url[:500] if job_url else None

        normalized_job = {
            'title': title,
            'location': location,
            'job_url': job_url,
            'job_description': '',  # Would need to fetch individual pages for full description
            'source': 'eightfold',
            'external_job_id': external_job_id[:255] if external_job_id else None,
            'posted_date': lastmod.split('T')[0] if lastmod else None,
        }
        jobs.append(normalized_job)

    return jobs


def fetch_jobs_from_ats(ats_type: str, company_slug: str) -> list:
    """
    Fetch jobs from the specified ATS.

    Args:
        ats_type: 'greenhouse', 'lever', 'ashby', 'smartrecruiters', 'workable', 'recruitee', 'workday', or 'custom'
        company_slug: The company identifier in the ATS

    Returns:
        List of normalized job dictionaries
    """
    fetchers = {
        'greenhouse': fetch_greenhouse_jobs,
        'lever': fetch_lever_jobs,
        'ashby': fetch_ashby_jobs,
        'smartrecruiters': fetch_smartrecruiters_jobs,
        'workable': fetch_workable_jobs,
        'recruitee': fetch_recruitee_jobs,
        'workday': fetch_workday_jobs,
        'apple': fetch_apple_jobs,
        'intuit': fetch_intuit_jobs,
        'adp': fetch_adp_jobs,
        'eightfold': fetch_eightfold_jobs,
    }

    if ats_type in fetchers:
        return fetchers[ats_type](company_slug)

    # For 'custom' ATS type, use the ScraperRegistry
    if ats_type == 'custom':
        return fetch_custom_scraper_jobs(company_slug)

    raise ValueError(f"Unsupported ATS type: {ats_type}. Supported: {', '.join(fetchers.keys())}, custom")


class SimpleBrowserPool:
    """
    Simple browser pool for PlaywrightScrapers.
    Creates a new browser context for each request.
    """

    def __init__(self):
        self._playwright = None
        self._browser = None

    async def _ensure_browser(self):
        """Ensure Playwright browser is launched."""
        if self._browser is None:
            try:
                from playwright.async_api import async_playwright
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-dev-shm-usage']
                )
            except ImportError:
                raise RuntimeError(
                    "Playwright is not installed. Install with: pip install playwright && playwright install chromium"
                )

    async def acquire(self):
        """Get a new browser page."""
        await self._ensure_browser()
        context = await self._browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        return page

    async def release(self, page):
        """Close a browser page and its context."""
        try:
            context = page.context
            await page.close()
            await context.close()
        except Exception:
            pass

    async def close(self):
        """Close browser and playwright."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()


def fetch_custom_scraper_jobs(company_slug: str) -> list:
    """
    Fetch jobs using custom scrapers from the ScraperRegistry.

    Args:
        company_slug: The company slug to look up in the registry

    Returns:
        List of normalized job dictionaries
    """
    import asyncio
    from scrapers.registry import ScraperRegistry, get_scraper
    from scrapers.base import ScraperType, PlaywrightScraper

    # Handle compound slugs like "google:wd1:External" - extract company name
    lookup_slug = company_slug.lower()
    if ':' in lookup_slug:
        lookup_slug = lookup_slug.split(':')[0]

    # Get the scraper class to check its type
    scraper_cls = ScraperRegistry.get(lookup_slug)

    if not scraper_cls:
        raise ValueError(f"No custom scraper found for '{company_slug}'. Available scrapers: {', '.join(ScraperRegistry.list_slugs()[:20])}...")

    # Check if this is a Playwright scraper (needs browser)
    is_playwright = scraper_cls.config.scraper_type == ScraperType.PLAYWRIGHT

    # Create browser pool if needed for Playwright scrapers
    browser_pool = None
    if is_playwright:
        browser_pool = SimpleBrowserPool()

    # Instantiate the scraper with browser_pool if needed
    scraper = scraper_cls(browser_pool=browser_pool)

    # Run the scraper
    async def run_scraper():
        try:
            result = await scraper.scrape()
            return result
        finally:
            # Cleanup browser pool if used
            if browser_pool:
                await browser_pool.close()

    try:
        # Run async scraper
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_scraper())
        finally:
            loop.close()

        if not result.success:
            raise ValueError(f"Scraper failed for '{company_slug}': {result.error_message}")

        # Convert ScrapedJob objects to dicts
        jobs = []
        for job in result.jobs:
            jobs.append({
                'title': job.title,
                'location': job.location,
                'job_url': job.job_url,
                'job_description': job.job_description or '',
                'source': 'custom',
                'external_job_id': job.external_job_id,
                'posted_date': job.posted_date.isoformat() if job.posted_date else None,
                'department': job.department,
            })

        return jobs

    except Exception as e:
        raise ValueError(f"Error running scraper for '{company_slug}': {str(e)}")


def get_company_name_from_slug(slug: str) -> str:
    """
    Convert a company slug to a display name.
    E.g., 'stripe' -> 'Stripe', 'acme-corp' -> 'Acme Corp'
    For Workday: 'nvidia:wd5:site' -> 'Nvidia'
    """
    # Handle Workday compound slug
    if ':' in slug:
        slug = slug.split(':')[0]
    name = slug.replace('-', ' ').replace('_', ' ')
    return name.title()


def get_supported_ats_info() -> dict:
    """
    Return information about supported ATS platforms.
    """
    return {
        'greenhouse': {
            'name': 'Greenhouse',
            'example_url': 'https://boards.greenhouse.io/stripe',
            'pattern': 'boards.greenhouse.io/{company}',
        },
        'lever': {
            'name': 'Lever',
            'example_url': 'https://jobs.lever.co/netflix',
            'pattern': 'jobs.lever.co/{company}',
        },
        'ashby': {
            'name': 'Ashby',
            'example_url': 'https://jobs.ashbyhq.com/notion',
            'pattern': 'jobs.ashbyhq.com/{company}',
        },
        'smartrecruiters': {
            'name': 'SmartRecruiters',
            'example_url': 'https://jobs.smartrecruiters.com/Visa',
            'pattern': 'jobs.smartrecruiters.com/{company}',
        },
        'workable': {
            'name': 'Workable',
            'example_url': 'https://apply.workable.com/deel',
            'pattern': 'apply.workable.com/{company}',
        },
        'recruitee': {
            'name': 'Recruitee',
            'example_url': 'https://nordhealth.recruitee.com',
            'pattern': '{company}.recruitee.com',
        },
        'workday': {
            'name': 'Workday',
            'example_url': 'https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite',
            'pattern': '{company}.wd{#}.myworkdayjobs.com/{site}',
        },
        'apple': {
            'name': 'Apple',
            'example_url': 'https://jobs.apple.com',
            'pattern': 'jobs.apple.com',
        },
        'intuit': {
            'name': 'Intuit',
            'example_url': 'https://jobs.intuit.com',
            'pattern': 'jobs.intuit.com',
        },
        'adp': {
            'name': 'ADP Workforce Now',
            'example_url': 'https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html?cid=xxx',
            'pattern': 'workforcenow.adp.com/?cid={company_id}',
        },
        'eightfold': {
            'name': 'Eightfold AI',
            'example_url': 'https://paypal.eightfold.ai/careers?domain=paypal.com',
            'pattern': '{company}.eightfold.ai/careers?domain={domain}',
        },
    }
