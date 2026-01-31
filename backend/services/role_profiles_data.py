"""
Predefined Role Profiles for Job Relevance Scoring

These profiles define the relevance criteria for common engineering roles.
They can be loaded into the database as seed data.

Each profile contains:
- slug: Unique identifier
- name: Display name
- description: Role description
- title_patterns: Job title matching rules
- positive_keywords: Keywords that boost relevance (weighted)
- negative_keywords: Keywords that reduce relevance
- seniority_config: Seniority preference settings
- relevance_threshold: Minimum score to be considered relevant

IMPORTANT: This is data-driven configuration. Adding new roles or modifying
existing ones does NOT require code changes - just update the profile data.
"""

from typing import Dict, Any, List


# ============== ROLE PROFILE DEFINITIONS ==============

ROLE_PROFILES: List[Dict[str, Any]] = [
    # ===========================================
    # DevOps / SRE / Platform
    # ===========================================
    {
        "slug": "devops",
        "name": "DevOps Engineer",
        "description": "Infrastructure automation, CI/CD, cloud platforms, and site reliability",
        "title_patterns": {
            "strong_match": [
                "devops", "dev ops", "sre", "site reliability",
                "platform engineer", "infrastructure engineer",
                "cloud engineer", "reliability engineer"
            ],
            "weak_match": [
                "systems engineer", "operations engineer", "build engineer",
                "release engineer", "deployment engineer", "automation engineer"
            ],
            "exclude": [
                "frontend", "mobile engineer", "ios engineer", "android engineer",
                "ui/ux", "product designer", "graphic designer", "data scientist",
                "machine learning", "ml engineer", "sales", "marketing", "hr"
            ]
        },
        "positive_keywords": {
            "high": [
                "kubernetes", "k8s", "docker", "terraform", "ansible",
                "ci/cd", "jenkins", "gitlab ci", "github actions",
                "aws", "gcp", "azure", "cloud", "infrastructure as code",
                "prometheus", "grafana", "datadog", "observability"
            ],
            "medium": [
                "linux", "unix", "bash", "python", "go", "golang",
                "monitoring", "alerting", "helm", "argocd", "istio",
                "microservices", "container", "orchestration",
                "puppet", "chef", "salt", "cloudformation", "pulumi"
            ],
            "low": [
                "automation", "scripting", "deployment", "pipeline",
                "distributed systems", "high availability", "scaling",
                "networking", "security", "vpc", "load balancer"
            ]
        },
        "negative_keywords": [
            "react", "angular", "vue", "swift", "kotlin", "ios sdk",
            "android sdk", "flutter", "react native", "ui design",
            "ux research", "figma", "sketch", "photoshop",
            "machine learning", "deep learning", "neural network",
            "tableau", "power bi", "salesforce"
        ],
        "seniority_config": {
            "preferred": ["senior", "staff", "lead", "principal"],
            "acceptable": ["mid"],
            "exclude": []
        },
        "relevance_threshold": 30.0
    },

    # ===========================================
    # Backend Engineering
    # ===========================================
    {
        "slug": "backend",
        "name": "Backend Engineer",
        "description": "Server-side development, APIs, databases, and distributed systems",
        "title_patterns": {
            "strong_match": [
                "backend engineer", "backend developer", "back-end engineer",
                "server engineer", "api engineer", "platform engineer",
                "software engineer, backend", "services engineer"
            ],
            "weak_match": [
                "software engineer", "software developer", "full stack",
                "fullstack", "application developer", "systems developer"
            ],
            "exclude": [
                "frontend engineer", "frontend developer", "ui engineer",
                "mobile engineer", "ios engineer", "android engineer",
                "devops", "sre", "data scientist", "ml engineer",
                "product designer", "ux designer"
            ]
        },
        "positive_keywords": {
            "high": [
                "python", "java", "go", "golang", "rust", "node.js", "nodejs",
                "api", "rest", "graphql", "grpc", "microservices",
                "postgresql", "mysql", "mongodb", "redis", "database",
                "distributed systems", "scalability"
            ],
            "medium": [
                "sql", "nosql", "kafka", "rabbitmq", "elasticsearch",
                "caching", "performance", "concurrency", "multithreading",
                "docker", "kubernetes", "aws", "gcp", "azure",
                "testing", "tdd", "unit tests"
            ],
            "low": [
                "architecture", "design patterns", "oop", "functional",
                "event-driven", "message queue", "pub/sub",
                "authentication", "authorization", "security"
            ]
        },
        "negative_keywords": [
            "react", "angular", "vue", "css", "sass", "tailwind",
            "ios", "swift", "android", "kotlin", "flutter",
            "figma", "sketch", "ui design", "ux research",
            "machine learning", "deep learning", "tensorflow", "pytorch"
        ],
        "seniority_config": {
            "preferred": ["senior", "staff", "lead", "principal"],
            "acceptable": ["mid", "junior"],
            "exclude": []
        },
        "relevance_threshold": 30.0
    },

    # ===========================================
    # Frontend Engineering
    # ===========================================
    {
        "slug": "frontend",
        "name": "Frontend Engineer",
        "description": "User interfaces, web applications, and client-side development",
        "title_patterns": {
            "strong_match": [
                "frontend engineer", "frontend developer", "front-end engineer",
                "ui engineer", "web developer", "javascript engineer",
                "react developer", "react engineer", "vue developer"
            ],
            "weak_match": [
                "software engineer", "full stack", "fullstack",
                "web engineer", "application developer"
            ],
            "exclude": [
                "backend engineer", "backend developer", "devops",
                "mobile engineer", "ios engineer", "android engineer",
                "data scientist", "ml engineer", "sre",
                "product designer", "ux designer"
            ]
        },
        "positive_keywords": {
            "high": [
                "react", "reactjs", "vue", "vuejs", "angular",
                "javascript", "typescript", "html", "css",
                "frontend", "front-end", "web", "ui",
                "next.js", "nextjs", "nuxt", "svelte"
            ],
            "medium": [
                "sass", "scss", "less", "tailwind", "styled-components",
                "webpack", "vite", "rollup", "babel",
                "redux", "mobx", "state management", "graphql",
                "jest", "cypress", "testing library", "playwright"
            ],
            "low": [
                "responsive", "accessibility", "a11y", "performance",
                "seo", "pwa", "progressive web app", "browser",
                "dom", "api integration", "rest", "ajax"
            ]
        },
        "negative_keywords": [
            "python", "java", "go", "rust", "c++", "c#",
            "kubernetes", "terraform", "ansible", "devops",
            "ios", "swift", "android", "kotlin",
            "machine learning", "data science", "etl"
        ],
        "seniority_config": {
            "preferred": ["senior", "staff", "lead"],
            "acceptable": ["mid", "junior"],
            "exclude": []
        },
        "relevance_threshold": 30.0
    },

    # ===========================================
    # Mobile Engineering
    # ===========================================
    {
        "slug": "mobile",
        "name": "Mobile Engineer",
        "description": "iOS, Android, and cross-platform mobile app development",
        "title_patterns": {
            "strong_match": [
                "mobile engineer", "mobile developer", "ios engineer",
                "ios developer", "android engineer", "android developer",
                "react native developer", "flutter developer"
            ],
            "weak_match": [
                "software engineer, mobile", "app developer",
                "application developer"
            ],
            "exclude": [
                "web developer", "frontend engineer", "backend engineer",
                "devops", "sre", "data scientist", "ml engineer",
                "embedded engineer"
            ]
        },
        "positive_keywords": {
            "high": [
                "ios", "android", "swift", "kotlin", "objective-c",
                "react native", "flutter", "mobile", "app",
                "xcode", "android studio", "swiftui", "jetpack compose"
            ],
            "medium": [
                "cocoapods", "gradle", "fastlane", "app store",
                "play store", "push notifications", "core data",
                "realm", "firebase", "mobile ui", "uikit"
            ],
            "low": [
                "offline", "caching", "performance", "animations",
                "gestures", "accessibility", "localization",
                "in-app purchase", "mobile testing", "appium"
            ]
        },
        "negative_keywords": [
            "web", "react.js", "vue", "angular", "node.js",
            "python", "java backend", "devops", "kubernetes",
            "machine learning", "data science", "embedded"
        ],
        "seniority_config": {
            "preferred": ["senior", "staff", "lead"],
            "acceptable": ["mid", "junior"],
            "exclude": []
        },
        "relevance_threshold": 30.0
    },

    # ===========================================
    # Data Engineering
    # ===========================================
    {
        "slug": "data",
        "name": "Data Engineer",
        "description": "Data pipelines, ETL, data warehousing, and big data systems",
        "title_patterns": {
            "strong_match": [
                "data engineer", "data platform engineer", "etl engineer",
                "big data engineer", "analytics engineer", "data infrastructure"
            ],
            "weak_match": [
                "software engineer, data", "data developer",
                "bi engineer", "data warehouse engineer"
            ],
            "exclude": [
                "data scientist", "data analyst", "ml engineer",
                "frontend", "mobile", "ios", "android",
                "devops", "product manager"
            ]
        },
        "positive_keywords": {
            "high": [
                "spark", "airflow", "kafka", "etl", "data pipeline",
                "data warehouse", "snowflake", "redshift", "bigquery",
                "databricks", "dbt", "data lake", "hadoop"
            ],
            "medium": [
                "python", "sql", "scala", "java", "pyspark",
                "aws", "gcp", "azure", "s3", "glue",
                "fivetran", "stitch", "data modeling", "star schema"
            ],
            "low": [
                "batch processing", "streaming", "real-time",
                "data quality", "data governance", "metadata",
                "orchestration", "scheduling", "monitoring"
            ]
        },
        "negative_keywords": [
            "react", "angular", "vue", "ios", "android",
            "frontend", "mobile", "ui design", "ux",
            "machine learning model", "deep learning", "neural network"
        ],
        "seniority_config": {
            "preferred": ["senior", "staff", "lead", "principal"],
            "acceptable": ["mid"],
            "exclude": []
        },
        "relevance_threshold": 30.0
    },

    # ===========================================
    # Machine Learning Engineering
    # ===========================================
    {
        "slug": "ml",
        "name": "ML Engineer",
        "description": "Machine learning systems, model training, and ML infrastructure",
        "title_patterns": {
            "strong_match": [
                "ml engineer", "machine learning engineer", "ai engineer",
                "deep learning engineer", "mlops engineer",
                "applied scientist", "research engineer"
            ],
            "weak_match": [
                "data scientist", "software engineer, ml",
                "ai/ml engineer", "computer vision engineer", "nlp engineer"
            ],
            "exclude": [
                "frontend", "backend", "mobile", "ios", "android",
                "devops", "sre", "data analyst", "bi analyst",
                "product designer"
            ]
        },
        "positive_keywords": {
            "high": [
                "machine learning", "deep learning", "pytorch", "tensorflow",
                "neural network", "nlp", "computer vision", "llm",
                "transformers", "hugging face", "model training", "mlops"
            ],
            "medium": [
                "python", "scikit-learn", "keras", "numpy", "pandas",
                "gpu", "cuda", "distributed training", "feature engineering",
                "model deployment", "ml pipeline", "kubeflow", "sagemaker"
            ],
            "low": [
                "statistics", "linear algebra", "optimization",
                "a/b testing", "experimentation", "recommendation",
                "classification", "regression", "clustering"
            ]
        },
        "negative_keywords": [
            "react", "angular", "vue", "ios", "android",
            "devops", "infrastructure", "frontend", "web developer",
            "product manager", "project manager", "sales"
        ],
        "seniority_config": {
            "preferred": ["senior", "staff", "lead", "principal"],
            "acceptable": ["mid"],
            "exclude": []
        },
        "relevance_threshold": 30.0
    },

    # ===========================================
    # Security Engineering
    # ===========================================
    {
        "slug": "security",
        "name": "Security Engineer",
        "description": "Application security, infrastructure security, and security operations",
        "title_patterns": {
            "strong_match": [
                "security engineer", "application security engineer",
                "infosec engineer", "cybersecurity engineer",
                "product security engineer", "security architect",
                "devsecops engineer", "penetration tester"
            ],
            "weak_match": [
                "software engineer, security", "cloud security engineer",
                "security analyst", "soc engineer", "security operations"
            ],
            "exclude": [
                "frontend", "mobile", "ios", "android",
                "data scientist", "ml engineer", "product designer",
                "sales engineer", "customer success"
            ]
        },
        "positive_keywords": {
            "high": [
                "security", "appsec", "infosec", "penetration testing",
                "vulnerability", "threat modeling", "secure coding",
                "owasp", "sast", "dast", "security architecture"
            ],
            "medium": [
                "authentication", "authorization", "encryption", "cryptography",
                "siem", "soc", "incident response", "compliance",
                "aws security", "cloud security", "kubernetes security"
            ],
            "low": [
                "audit", "risk assessment", "security review",
                "identity management", "iam", "zero trust",
                "firewall", "network security", "endpoint security"
            ]
        },
        "negative_keywords": [
            "react", "angular", "vue", "frontend developer",
            "ios developer", "android developer", "mobile",
            "machine learning", "data science", "product design"
        ],
        "seniority_config": {
            "preferred": ["senior", "staff", "lead", "principal"],
            "acceptable": ["mid"],
            "exclude": []
        },
        "relevance_threshold": 30.0
    },

    # ===========================================
    # Full Stack Engineering
    # ===========================================
    {
        "slug": "fullstack",
        "name": "Full Stack Engineer",
        "description": "End-to-end development spanning frontend and backend systems",
        "title_patterns": {
            "strong_match": [
                "full stack engineer", "fullstack engineer", "full-stack developer",
                "fullstack developer", "software engineer, fullstack"
            ],
            "weak_match": [
                "software engineer", "web developer", "application developer",
                "product engineer"
            ],
            "exclude": [
                "devops", "sre", "mobile only", "ios only", "android only",
                "data scientist", "ml engineer", "product designer"
            ]
        },
        "positive_keywords": {
            "high": [
                "full stack", "fullstack", "full-stack",
                "react", "vue", "angular", "node.js", "python",
                "typescript", "javascript", "api", "database"
            ],
            "medium": [
                "frontend", "backend", "postgresql", "mongodb",
                "rest", "graphql", "aws", "docker",
                "next.js", "django", "rails", "express"
            ],
            "low": [
                "html", "css", "sql", "testing",
                "ci/cd", "agile", "scrum", "git"
            ]
        },
        "negative_keywords": [
            "mobile only", "ios only", "android only",
            "machine learning only", "data science only",
            "devops only", "infrastructure only"
        ],
        "seniority_config": {
            "preferred": ["senior", "staff", "lead"],
            "acceptable": ["mid", "junior"],
            "exclude": []
        },
        "relevance_threshold": 25.0  # Lower threshold as it's broader
    },
]


def get_profile_by_slug(slug: str) -> Dict[str, Any]:
    """Get a role profile by its slug."""
    for profile in ROLE_PROFILES:
        if profile["slug"] == slug:
            return profile
    return None


def get_all_profiles() -> List[Dict[str, Any]]:
    """Get all role profiles."""
    return ROLE_PROFILES


def get_profile_slugs() -> List[str]:
    """Get list of all profile slugs."""
    return [p["slug"] for p in ROLE_PROFILES]


def get_profile_names() -> Dict[str, str]:
    """Get mapping of slug to display name."""
    return {p["slug"]: p["name"] for p in ROLE_PROFILES}
