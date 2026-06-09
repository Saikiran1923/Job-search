"""Resume optimization helpers for the API."""

from __future__ import annotations

from pathlib import Path

from .ats import select_role_bullets
from .keywords import extract_known_skills, important_terms, normalize_role
from .models import RoleLibrary


def _score_text(text: str, skills: list[str], keywords: list[str]) -> int:
    lowered = text.lower()
    skill_matches = [skill for skill in skills if skill.lower() in lowered]
    keyword_matches = [keyword for keyword in keywords if keyword.lower() in lowered]
    skill_score = len(skill_matches) / len(skills) if skills else 0.75
    keyword_score = len(keyword_matches) / len(keywords) if keywords else 0.75
    return max(0, min(100, round((skill_score * 0.7 + keyword_score * 0.3) * 100)))


def analyze_resume_text(
    resume_text: str,
    job_description: str,
    role: str = "General IT",
    roles_dir: Path = Path("data/roles"),
) -> dict[str, object]:
    """Compare raw resume text against a job description."""

    job_text = f"{role}\n{job_description}"
    job_skills = extract_known_skills(job_text)
    resume_skills = set(extract_known_skills(resume_text))
    matched_skills = sorted(skill for skill in job_skills if skill in resume_skills)
    missing_skills = sorted(skill for skill in job_skills if skill not in resume_skills)
    keywords = important_terms(job_text, limit=20)

    role_path = roles_dir / f"{normalize_role(role)}.json"
    fallback_path = roles_dir / "general_it.json"
    library = RoleLibrary.from_path(role_path if role_path.exists() else fallback_path, role)
    selected_bullets = select_role_bullets(library, job_text, missing_skills, limit=5)
    original_score = _score_text(resume_text, job_skills, keywords)
    optimized_text = "\n".join([resume_text, *selected_bullets])
    optimized_score = _score_text(optimized_text, job_skills, keywords)

    summary_keywords = ", ".join((matched_skills + missing_skills)[:8])
    tailored_summary = (
        f"IT professional aligned with {role} requirements, bringing experience across "
        f"{summary_keywords or 'core technical delivery, collaboration, and problem solving'}."
    )

    return {
        "role": role,
        "original_ats_score": original_score,
        "optimized_ats_score": optimized_score,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "important_keywords": keywords,
        "suggested_bullets": selected_bullets,
        "tailored_summary": tailored_summary,
        "review_required": bool(selected_bullets and optimized_score < 85),
    }
