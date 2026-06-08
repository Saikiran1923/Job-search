"""Compliant job source helpers.

The assistant generates search URLs for review or for use with official APIs/exports.
It does not bypass website protections or automate submissions on third-party sites.
"""

from __future__ import annotations

from urllib.parse import quote_plus

from .keywords import ALL_IT_ROLES


SUPPORTED_PLATFORMS = {
    "linkedin": "https://www.linkedin.com/jobs/search/?keywords={query}",
    "indeed": "https://www.indeed.com/jobs?q={query}",
    "dice": "https://www.dice.com/jobs?q={query}",
    "glassdoor": "https://www.glassdoor.com/Job/jobs.htm?sc.keyword={query}",
    "monster": "https://www.monster.com/jobs/search?q={query}",
    "careerbuilder": "https://www.careerbuilder.com/jobs?keywords={query}",
    "ziprecruiter": "https://www.ziprecruiter.com/jobs-search?search={query}",
    "company_portals": "https://www.google.com/search?q={query}+careers+jobs",
}


def expand_roles(roles: list[str], all_it: bool = False) -> list[str]:
    if all_it:
        return ALL_IT_ROLES
    cleaned = [role.strip() for role in roles if role.strip()]
    return cleaned or ALL_IT_ROLES


def build_search_links(
    roles: list[str],
    platforms: list[str] | None = None,
    location: str = "",
    all_it: bool = False,
) -> dict[str, dict[str, str]]:
    selected_roles = expand_roles(roles, all_it=all_it)
    selected_platforms = platforms or list(SUPPORTED_PLATFORMS)
    links: dict[str, dict[str, str]] = {}
    for role in selected_roles:
        query = f"{role} {location}".strip()
        encoded = quote_plus(query)
        links[role] = {}
        for platform in selected_platforms:
            if platform not in SUPPORTED_PLATFORMS:
                raise ValueError(f"Unsupported platform '{platform}'")
            links[role][platform] = SUPPORTED_PLATFORMS[platform].format(query=encoded)
    return links
