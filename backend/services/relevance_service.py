"""
Relevance Scoring Service

Computes relevance scores for job-role profile combinations.
This is the core engine for role-aware job discovery.

Scoring Algorithm:
------------------
score = title_score + keyword_score + seniority_bonus - penalties

Components:
- Title Score (0-40): Based on job title matching role patterns
- Keyword Score (0-50): Based on positive keywords in description
- Seniority Bonus (-10 to +15): Based on seniority alignment
- Penalties (0 to -30): Based on negative keywords

Final score normalized to 0-100 scale.
Jobs with score >= threshold are marked as relevant.

Design Principles:
- Deterministic: Same inputs always produce same score
- Explainable: Score breakdown shows why a job scored high/low
- Role-specific: Same job scores differently for different roles
- Extensible: Easy to add new signals or adjust weights
"""

import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache


@dataclass
class RelevanceResult:
    """Result of relevance scoring for a job-role combination."""
    relevance_score: float  # 0-100 scale
    is_relevant: bool  # Score >= threshold
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    matched_title_patterns: List[str] = field(default_factory=list)
    matched_keywords: List[str] = field(default_factory=list)
    negative_matches: List[str] = field(default_factory=list)
    explanation: str = ""


class RelevanceScorer:
    """
    Computes relevance scores for job postings based on role profiles.

    Usage:
        scorer = RelevanceScorer()
        result = scorer.score(job_title, job_description, role_profile)
    """

    # Scoring weights (configurable)
    WEIGHTS = {
        "title_strong_match": 40,
        "title_weak_match": 20,
        "title_exclude_penalty": -50,
        "keyword_high": 8,
        "keyword_medium": 4,
        "keyword_low": 2,
        "keyword_max_score": 50,
        "negative_keyword_penalty": -5,
        "negative_keyword_max_penalty": -30,
        "seniority_preferred_bonus": 15,
        "seniority_acceptable_bonus": 5,
        "seniority_exclude_penalty": -20,
    }

    # Common seniority patterns
    SENIORITY_PATTERNS = {
        "intern": r"\b(intern|internship)\b",
        "junior": r"\b(junior|jr\.?|entry[- ]?level|associate)\b",
        "mid": r"\b(mid[- ]?level|intermediate)\b",
        "senior": r"\b(senior|sr\.?)\b",
        "staff": r"\b(staff)\b",
        "principal": r"\b(principal|distinguished)\b",
        "lead": r"\b(lead|tech lead|team lead)\b",
        "manager": r"\b(manager|engineering manager|em)\b",
        "director": r"\b(director)\b",
        "vp": r"\b(vp|vice president)\b",
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """Initialize scorer with optional custom weights."""
        if weights:
            self.WEIGHTS.update(weights)

    def score(
        self,
        job_title: str,
        job_description: str,
        role_profile: Dict[str, Any],
        user_preferences: Optional[Dict[str, Any]] = None
    ) -> RelevanceResult:
        """
        Compute relevance score for a job given a role profile.

        Args:
            job_title: The job posting title
            job_description: The full job description text
            role_profile: Dict with title_patterns, positive_keywords, negative_keywords, etc.
            user_preferences: Optional user-specific overrides

        Returns:
            RelevanceResult with score, breakdown, and explanation
        """
        # Normalize text for matching
        title_lower = job_title.lower() if job_title else ""
        desc_lower = job_description.lower() if job_description else ""
        combined_text = f"{title_lower} {desc_lower}"

        # Initialize result
        breakdown = {
            "title_score": 0,
            "keyword_score": 0,
            "seniority_bonus": 0,
            "penalties": 0,
        }
        matched_title_patterns = []
        matched_keywords = []
        negative_matches = []
        excluded = False  # Flag if job should be excluded entirely

        # 1. Title Matching
        title_patterns = role_profile.get("title_patterns", {})
        title_score, title_matches, title_excluded = self._score_title(
            title_lower, title_patterns
        )
        breakdown["title_score"] = title_score
        matched_title_patterns = title_matches
        if title_excluded:
            excluded = True

        # 2. Keyword Matching
        positive_keywords = role_profile.get("positive_keywords", {})
        keyword_score, keyword_matches = self._score_keywords(
            combined_text, positive_keywords
        )
        breakdown["keyword_score"] = keyword_score
        matched_keywords = keyword_matches

        # 3. Negative Keywords
        negative_keywords = role_profile.get("negative_keywords", [])
        if user_preferences:
            # Add user's blocked keywords
            negative_keywords = list(negative_keywords) + user_preferences.get("blocked_keywords", [])

        penalty, neg_matches = self._score_negative_keywords(
            combined_text, negative_keywords
        )
        breakdown["penalties"] = penalty
        negative_matches = neg_matches

        # 4. Seniority Alignment
        seniority_config = role_profile.get("seniority_config", {})
        user_seniority = None
        if user_preferences:
            user_seniority = user_preferences.get("target_seniority")

        seniority_bonus = self._score_seniority(
            title_lower, seniority_config, user_seniority
        )
        breakdown["seniority_bonus"] = seniority_bonus

        # 5. Calculate raw score
        raw_score = (
            breakdown["title_score"]
            + breakdown["keyword_score"]
            + breakdown["seniority_bonus"]
            + breakdown["penalties"]
        )

        # 6. Normalize to 0-100
        # Max possible: 40 (title) + 50 (keywords) + 15 (seniority) = 105
        # We cap at 100 and floor at 0
        relevance_score = max(0, min(100, raw_score))

        # If title excluded, force low score
        if excluded:
            relevance_score = min(relevance_score, 10)

        # 7. Determine relevance
        threshold = role_profile.get("relevance_threshold", 30.0)
        is_relevant = relevance_score >= threshold and not excluded

        # 8. Generate explanation
        explanation = self._generate_explanation(
            relevance_score, breakdown, matched_title_patterns,
            matched_keywords, negative_matches, is_relevant
        )

        return RelevanceResult(
            relevance_score=round(relevance_score, 2),
            is_relevant=is_relevant,
            score_breakdown=breakdown,
            matched_title_patterns=matched_title_patterns,
            matched_keywords=matched_keywords,
            negative_matches=negative_matches,
            explanation=explanation
        )

    def _score_title(
        self, title: str, patterns: Dict[str, List[str]]
    ) -> Tuple[float, List[str], bool]:
        """
        Score job title against role patterns.

        Returns: (score, matched_patterns, is_excluded)
        """
        score = 0
        matched = []
        excluded = False

        # Check for exclusion patterns first
        exclude_patterns = patterns.get("exclude", [])
        for pattern in exclude_patterns:
            if self._pattern_match(title, pattern):
                excluded = True
                score = self.WEIGHTS["title_exclude_penalty"]
                matched.append(f"-{pattern}")
                break

        if not excluded:
            # Check strong matches
            strong_patterns = patterns.get("strong_match", [])
            for pattern in strong_patterns:
                if self._pattern_match(title, pattern):
                    score = max(score, self.WEIGHTS["title_strong_match"])
                    matched.append(f"+{pattern}")

            # Check weak matches (only if no strong match)
            if score < self.WEIGHTS["title_strong_match"]:
                weak_patterns = patterns.get("weak_match", [])
                for pattern in weak_patterns:
                    if self._pattern_match(title, pattern):
                        score = max(score, self.WEIGHTS["title_weak_match"])
                        matched.append(f"~{pattern}")

        return score, matched, excluded

    def _score_keywords(
        self, text: str, keywords: Dict[str, List[str]]
    ) -> Tuple[float, List[str]]:
        """
        Score description against positive keywords.

        Returns: (score, matched_keywords)
        """
        score = 0
        matched = []

        # High weight keywords
        high_keywords = keywords.get("high", [])
        for kw in high_keywords:
            if self._pattern_match(text, kw):
                score += self.WEIGHTS["keyword_high"]
                matched.append(f"++{kw}")

        # Medium weight keywords
        medium_keywords = keywords.get("medium", [])
        for kw in medium_keywords:
            if self._pattern_match(text, kw):
                score += self.WEIGHTS["keyword_medium"]
                matched.append(f"+{kw}")

        # Low weight keywords
        low_keywords = keywords.get("low", [])
        for kw in low_keywords:
            if self._pattern_match(text, kw):
                score += self.WEIGHTS["keyword_low"]
                matched.append(f"~{kw}")

        # Cap at maximum
        score = min(score, self.WEIGHTS["keyword_max_score"])

        return score, matched

    def _score_negative_keywords(
        self, text: str, keywords: List[str]
    ) -> Tuple[float, List[str]]:
        """
        Apply penalties for negative keywords.

        Returns: (penalty, matched_keywords)
        """
        penalty = 0
        matched = []

        for kw in keywords:
            if self._pattern_match(text, kw):
                penalty += self.WEIGHTS["negative_keyword_penalty"]
                matched.append(kw)

        # Cap penalty
        penalty = max(penalty, self.WEIGHTS["negative_keyword_max_penalty"])

        return penalty, matched

    def _score_seniority(
        self,
        title: str,
        config: Dict[str, List[str]],
        user_preference: Optional[str] = None
    ) -> float:
        """
        Score based on seniority alignment.

        Returns: seniority bonus/penalty
        """
        # Detect seniority in title
        detected_seniority = None
        for level, pattern in self.SENIORITY_PATTERNS.items():
            if re.search(pattern, title, re.IGNORECASE):
                detected_seniority = level
                break

        if not detected_seniority:
            return 0

        # Check against config
        preferred = config.get("preferred", [])
        acceptable = config.get("acceptable", [])
        exclude = config.get("exclude", [])

        if detected_seniority in exclude:
            return self.WEIGHTS["seniority_exclude_penalty"]
        elif detected_seniority in preferred:
            return self.WEIGHTS["seniority_preferred_bonus"]
        elif detected_seniority in acceptable:
            return self.WEIGHTS["seniority_acceptable_bonus"]

        # Check user preference if available
        if user_preference and detected_seniority == user_preference:
            return self.WEIGHTS["seniority_preferred_bonus"]

        return 0

    @staticmethod
    @lru_cache(maxsize=1000)
    def _compile_pattern(pattern: str) -> re.Pattern:
        """Compile and cache regex pattern."""
        escaped = re.escape(pattern.lower())
        return re.compile(rf"\b{escaped}\b", re.IGNORECASE)

    def _pattern_match(self, text: str, pattern: str) -> bool:
        """
        Check if pattern matches in text.
        Supports word boundary matching with cached regex.
        """
        compiled = self._compile_pattern(pattern)
        return bool(compiled.search(text))

    def _generate_explanation(
        self,
        score: float,
        breakdown: Dict[str, float],
        title_matches: List[str],
        keyword_matches: List[str],
        negative_matches: List[str],
        is_relevant: bool
    ) -> str:
        """Generate human-readable explanation of the score."""
        parts = []

        if is_relevant:
            parts.append(f"Relevance: {score:.0f}/100 (RELEVANT)")
        else:
            parts.append(f"Relevance: {score:.0f}/100 (not relevant)")

        if title_matches:
            parts.append(f"Title matches: {', '.join(title_matches)}")

        if keyword_matches:
            top_keywords = keyword_matches[:5]
            parts.append(f"Keywords: {', '.join(top_keywords)}")
            if len(keyword_matches) > 5:
                parts.append(f"  +{len(keyword_matches) - 5} more")

        if negative_matches:
            parts.append(f"Negative signals: {', '.join(negative_matches)}")

        if breakdown["seniority_bonus"] != 0:
            if breakdown["seniority_bonus"] > 0:
                parts.append(f"Seniority: +{breakdown['seniority_bonus']:.0f}")
            else:
                parts.append(f"Seniority: {breakdown['seniority_bonus']:.0f}")

        return " | ".join(parts)


# Global scorer instance (reused for performance)
_scorer = RelevanceScorer()


# Convenience functions for use in routes

def compute_job_relevance(
    job,  # Job model instance
    role_profile,  # RoleProfile model instance or dict
    user_preferences: Optional[Dict] = None
) -> RelevanceResult:
    """
    Compute relevance for a Job model instance.

    Args:
        job: Job model with title and job_description
        role_profile: RoleProfile model or dict with scoring config
        user_preferences: Optional user-specific overrides

    Returns:
        RelevanceResult
    """
    # Convert model to dict if needed
    if hasattr(role_profile, "__dict__"):
        profile_dict = {
            "title_patterns": role_profile.title_patterns or {},
            "positive_keywords": role_profile.positive_keywords or {},
            "negative_keywords": role_profile.negative_keywords or [],
            "seniority_config": role_profile.seniority_config or {},
            "relevance_threshold": role_profile.relevance_threshold or 30.0,
        }
    else:
        profile_dict = role_profile

    return _scorer.score(
        job_title=job.title or "",
        job_description=job.job_description or "",
        role_profile=profile_dict,
        user_preferences=user_preferences
    )


def compute_relevance_batch(
    jobs: List,  # List of Job models
    role_profile,  # RoleProfile model or dict
    user_preferences: Optional[Dict] = None
) -> List[Tuple[Any, RelevanceResult]]:
    """
    Compute relevance for multiple jobs.

    Returns list of (job, RelevanceResult) tuples sorted by score DESC.
    """
    results = []
    for job in jobs:
        result = compute_job_relevance(job, role_profile, user_preferences)
        results.append((job, result))

    # Sort by relevance score descending
    results.sort(key=lambda x: x[1].relevance_score, reverse=True)

    return results


def filter_relevant_jobs(
    jobs: List,
    role_profile,
    user_preferences: Optional[Dict] = None,
    limit: int = 50
) -> List[Tuple[Any, RelevanceResult]]:
    """
    Filter and rank jobs by relevance.

    Returns only relevant jobs, sorted by score, limited to top N.
    """
    scored = compute_relevance_batch(jobs, role_profile, user_preferences)

    # Filter to relevant only
    relevant = [(job, result) for job, result in scored if result.is_relevant]

    # Apply limit
    return relevant[:limit]


# Example usage demonstration
if __name__ == "__main__":
    # Example role profile for DevOps
    devops_profile = {
        "title_patterns": {
            "strong_match": ["devops", "sre", "site reliability", "platform engineer", "infrastructure engineer"],
            "weak_match": ["cloud engineer", "systems engineer", "operations"],
            "exclude": ["frontend", "mobile", "ios", "android", "ui/ux designer"]
        },
        "positive_keywords": {
            "high": ["kubernetes", "k8s", "docker", "terraform", "ansible", "ci/cd", "jenkins", "aws", "gcp", "azure"],
            "medium": ["linux", "monitoring", "prometheus", "grafana", "helm", "argocd", "python", "bash"],
            "low": ["automation", "infrastructure", "deployment", "cloud", "scripting"]
        },
        "negative_keywords": ["react", "angular", "vue", "swift", "kotlin", "ios sdk", "android sdk"],
        "seniority_config": {
            "preferred": ["senior", "staff", "lead"],
            "acceptable": ["mid"],
            "exclude": ["intern"]
        },
        "relevance_threshold": 30.0
    }

    # Example jobs
    jobs_data = [
        {
            "title": "Senior DevOps Engineer",
            "description": "We need a DevOps engineer with Kubernetes, Docker, and AWS experience. You'll build CI/CD pipelines with Jenkins and manage infrastructure with Terraform."
        },
        {
            "title": "Frontend Developer",
            "description": "Build beautiful UIs with React and TypeScript. Work with our design team to implement pixel-perfect interfaces."
        },
        {
            "title": "Cloud Infrastructure Engineer",
            "description": "Manage our AWS infrastructure, implement monitoring with Prometheus and Grafana, and automate deployments."
        }
    ]

    scorer = RelevanceScorer()

    print("=" * 60)
    print("RELEVANCE SCORING DEMONSTRATION - DevOps Profile")
    print("=" * 60)

    for job in jobs_data:
        result = scorer.score(job["title"], job["description"], devops_profile)
        print(f"\nJob: {job['title']}")
        print(f"  Score: {result.relevance_score:.0f}/100")
        print(f"  Relevant: {result.is_relevant}")
        print(f"  Title matches: {result.matched_title_patterns}")
        print(f"  Keywords: {result.matched_keywords[:5]}")
        if result.negative_matches:
            print(f"  Negative: {result.negative_matches}")
        print(f"  Breakdown: {result.score_breakdown}")
