"""Keyword and role catalogs used for matching and search-link generation."""

from __future__ import annotations

import re
from collections import Counter


ALL_IT_ROLES = [
    "Software Engineer",
    "Backend Developer",
    "Frontend Developer",
    "Full Stack Developer",
    "Data Engineer",
    "Azure Data Engineer",
    "Data Scientist",
    "Machine Learning Engineer",
    "DevOps Engineer",
    "Cloud Engineer",
    "Cybersecurity Analyst",
    "QA Engineer",
    "Business Intelligence Analyst",
    "Database Administrator",
    "Systems Administrator",
    "Network Engineer",
    "IT Support Specialist",
]


SKILL_TERMS = {
    "python",
    "java",
    "javascript",
    "typescript",
    "c#",
    "c++",
    "go",
    "ruby",
    "php",
    "scala",
    "sql",
    "nosql",
    "postgresql",
    "mysql",
    "sql server",
    "oracle",
    "mongodb",
    "redis",
    "snowflake",
    "databricks",
    "spark",
    "pyspark",
    "hadoop",
    "kafka",
    "airflow",
    "dbt",
    "etl",
    "elt",
    "data warehouse",
    "data lake",
    "power bi",
    "tableau",
    "looker",
    "excel",
    "aws",
    "azure",
    "gcp",
    "docker",
    "kubernetes",
    "terraform",
    "jenkins",
    "github actions",
    "gitlab ci",
    "linux",
    "bash",
    "powershell",
    "react",
    "angular",
    "vue",
    "node.js",
    "express",
    "django",
    "flask",
    "fastapi",
    "spring boot",
    ".net",
    "rest",
    "graphql",
    "microservices",
    "api",
    "html",
    "css",
    "tailwind",
    "machine learning",
    "deep learning",
    "nlp",
    "computer vision",
    "tensorflow",
    "pytorch",
    "scikit-learn",
    "pandas",
    "numpy",
    "matplotlib",
    "cybersecurity",
    "siem",
    "splunk",
    "soc",
    "iam",
    "oauth",
    "saml",
    "penetration testing",
    "vulnerability management",
    "qa",
    "test automation",
    "selenium",
    "playwright",
    "cypress",
    "junit",
    "pytest",
    "agile",
    "scrum",
    "jira",
    "git",
    "ci/cd",
    "devops",
    "observability",
    "prometheus",
    "grafana",
}


STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "our",
    "that",
    "the",
    "this",
    "to",
    "with",
    "you",
    "your",
    "will",
    "we",
}


TOKEN_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9+#./-]*")


def normalize_role(role: str) -> str:
    """Normalize a role name to match /data/roles/{role}.json."""

    return re.sub(r"[^a-z0-9]+", "_", role.lower()).strip("_")


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def extract_known_skills(text: str) -> list[str]:
    """Find known technology and skill terms in text."""

    lowered = normalize_text(text)
    found = []
    for term in sorted(SKILL_TERMS, key=len, reverse=True):
        pattern = rf"(?<![a-z0-9+#./-]){re.escape(term)}(?![a-z0-9+#./-])"
        if re.search(pattern, lowered):
            found.append(term)
    return sorted(set(found))


def important_terms(text: str, limit: int = 25) -> list[str]:
    """Return high-signal job terms not already captured as skills."""

    tokens = [
        token.lower()
        for token in TOKEN_PATTERN.findall(text)
        if len(token) > 2 and token.lower() not in STOP_WORDS
    ]
    counts = Counter(tokens)
    known = set(extract_known_skills(text))
    terms = [term for term, _ in counts.most_common(limit * 2) if term not in known]
    return terms[:limit]
