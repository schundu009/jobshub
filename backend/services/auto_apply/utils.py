"""
Utility functions for auto-apply functionality.
"""

import os
import re
from typing import Optional, Dict
from datetime import datetime


def get_ats_type_from_url(url: str) -> Optional[str]:
    """
    Determine the ATS type from a job URL.

    Args:
        url: Job application URL

    Returns:
        ATS type string or None if unknown
    """
    url_lower = url.lower()

    if "greenhouse.io" in url_lower or "boards.greenhouse.io" in url_lower:
        return "greenhouse"
    elif "lever.co" in url_lower or "jobs.lever.co" in url_lower:
        return "lever"
    elif "workday" in url_lower or "myworkdayjobs" in url_lower:
        return "workday"
    elif "icims" in url_lower:
        return "icims"
    elif "taleo" in url_lower:
        return "taleo"
    elif "brassring" in url_lower:
        return "brassring"
    elif "jobvite" in url_lower:
        return "jobvite"
    elif "smartrecruiters" in url_lower:
        return "smartrecruiters"
    elif "ashby" in url_lower:
        return "ashby"

    return None


def is_supported_ats(url: str) -> bool:
    """Check if the ATS type is supported for auto-apply."""
    # Supported ATS platforms: Greenhouse, Lever, Workday
    supported = {"greenhouse", "lever", "workday"}
    ats_type = get_ats_type_from_url(url)
    return ats_type in supported


def get_application_url(job_url: str, ats_type: str) -> str:
    """
    Convert a job URL to the application form URL.

    Args:
        job_url: Original job posting URL
        ats_type: Type of ATS

    Returns:
        Application form URL
    """
    if ats_type == "lever":
        # Lever: add /apply to the URL
        if not job_url.endswith("/apply"):
            return job_url.rstrip("/") + "/apply"
        return job_url

    elif ats_type == "greenhouse":
        # Greenhouse: the job page usually has an Apply button
        # or we can construct the apply URL
        # Format: https://boards.greenhouse.io/{company}/jobs/{job_id}
        # Apply: https://boards.greenhouse.io/{company}/jobs/{job_id}#application
        if "#application" not in job_url:
            return job_url + "#application"
        return job_url

    return job_url


def extract_company_slug_from_url(url: str, ats_type: str) -> Optional[str]:
    """
    Extract the company slug from an ATS URL.

    Args:
        url: Job URL
        ats_type: Type of ATS

    Returns:
        Company slug or None
    """
    if ats_type == "greenhouse":
        # Format: https://boards.greenhouse.io/{company}/jobs/{job_id}
        match = re.search(r'greenhouse\.io/([^/]+)/jobs', url)
        if match:
            return match.group(1)

    elif ats_type == "lever":
        # Format: https://jobs.lever.co/{company}/{job_id}
        match = re.search(r'lever\.co/([^/]+)/', url)
        if match:
            return match.group(1)

    return None


def format_phone_number(phone: str) -> str:
    """
    Format a phone number for form input.

    Args:
        phone: Raw phone number

    Returns:
        Formatted phone number
    """
    if not phone:
        return ""

    # Remove all non-digit characters
    digits = re.sub(r'\D', '', phone)

    # Format as (XXX) XXX-XXXX for US numbers
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    elif len(digits) == 11 and digits[0] == '1':
        return f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"

    # Return as-is for other formats
    return phone


def get_screenshot_path(ats_type: str, job_id: int, status: str) -> str:
    """
    Generate a screenshot file path.

    Args:
        ats_type: Type of ATS
        job_id: Job database ID
        status: Status string (e.g., "confirmation", "error")

    Returns:
        Full path to screenshot file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshots_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "data", "screenshots"
    )
    os.makedirs(screenshots_dir, exist_ok=True)

    filename = f"job_{job_id}_{ats_type}_{status}_{timestamp}.png"
    return os.path.join(screenshots_dir, filename)


def match_question_pattern(question_text: str, patterns: Dict[str, str]) -> Optional[str]:
    """
    Match a question against stored patterns and return the answer.

    Args:
        question_text: The question text to match
        patterns: Dict of patterns -> answers

    Returns:
        Matching answer or None
    """
    question_lower = question_text.lower()

    for pattern, answer in patterns.items():
        # Simple substring match
        if pattern.lower() in question_lower:
            return answer

        # Try regex pattern
        try:
            if re.search(pattern, question_text, re.IGNORECASE):
                return answer
        except re.error:
            pass

    return None


# Common question patterns for work authorization
WORK_AUTH_PATTERNS = {
    r"authorized.*work.*united states": "us_authorized",
    r"legally.*work.*us": "us_authorized",
    r"require.*sponsor": "requires_sponsorship",
    r"visa.*sponsor": "requires_sponsorship",
    r"work.*visa": "requires_sponsorship",
}


def identify_question_type(question_text: str) -> Optional[str]:
    """
    Identify the type of question from its text.

    Args:
        question_text: Question text

    Returns:
        Question type (e.g., "us_authorized", "requires_sponsorship") or None
    """
    question_lower = question_text.lower()

    for pattern, q_type in WORK_AUTH_PATTERNS.items():
        if re.search(pattern, question_lower):
            return q_type

    return None


def validate_profile_completeness(profile: Dict) -> Dict:
    """
    Check if the profile has all required fields for auto-apply.

    Args:
        profile: User profile dictionary

    Returns:
        Dict with completeness info and missing fields
    """
    required_fields = {
        "first_name": bool(profile.get("first_name")),
        "last_name": bool(profile.get("last_name")),
        "email": bool(profile.get("email")),
        "phone": bool(profile.get("phone")),
    }

    recommended_fields = {
        "city": bool(profile.get("city")),
        "state": bool(profile.get("state")),
        "linkedin_url": bool(profile.get("linkedin_url")),
        "us_authorized": profile.get("us_authorized") is not None,
        "requires_sponsorship": profile.get("requires_sponsorship") is not None,
    }

    # Get list of missing required fields
    missing_fields = [field for field, complete in required_fields.items() if not complete]

    return {
        "required": required_fields,
        "recommended": recommended_fields,
        "all_required_complete": all(required_fields.values()),
        "missing_fields": missing_fields,
        "completeness_score": (
            sum(required_fields.values()) + sum(recommended_fields.values())
        ) / (len(required_fields) + len(recommended_fields)) * 100,
    }
