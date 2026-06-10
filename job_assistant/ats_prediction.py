"""Weighted ATS prediction engine and resume suggestion flow."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any
import re

from .keywords import extract_known_skills, important_terms, normalize_text


@dataclass
class ResumeSuggestion:
    id: str
    section_name: str
    current_text: str
    suggested_text: str
    reason_for_change: str
    keywords_added: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _text_from_job(job_details: dict[str, Any] | str) -> str:
    if isinstance(job_details, str):
        return job_details
    fields = [
        "job_title",
        "company_name",
        "full_job_description",
        "responsibilities",
        "required_qualifications",
        "preferred_qualifications",
        "required_skills",
        "preferred_skills",
    ]
    parts: list[str] = []
    for field in fields:
        value = job_details.get(field)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif value:
            parts.append(str(value))
    return "\n".join(parts)


def _job_title(job_details: dict[str, Any] | str) -> str:
    return str(job_details.get("job_title", "")) if isinstance(job_details, dict) else ""


def _sections(resume_text: str) -> dict[str, str]:
    section_names = ["summary", "skills", "experience", "education", "projects", "certifications"]
    sections = {name: "" for name in section_names}
    current = "summary"
    for line in resume_text.splitlines():
        normalized = normalize_text(line).strip("#: ")
        matched = next((name for name in section_names if name in normalized and len(normalized) < 40), None)
        if matched:
            current = matched
            continue
        sections[current] = (sections[current] + "\n" + line).strip()
    if not any(sections.values()):
        sections["summary"] = resume_text[:500]
    return sections


def _formatting_issues(resume_text: str) -> list[str]:
    issues = []
    if "\t" in resume_text:
        issues.append("Tabs detected; use simple spaces for ATS readability.")
    if re.search(r"[│┌┐└┘]", resume_text):
        issues.append("Table/box drawing characters detected; use plain text sections.")
    if len(re.findall(r"https?://", resume_text)) > 6:
        issues.append("Too many links may distract from ATS parsing.")
    if len(resume_text.split()) < 120:
        issues.append("Resume text appears short; add complete summary, skills, experience, and education sections.")
    if not re.search(r"\b(skills|technical skills)\b", resume_text, flags=re.IGNORECASE):
        issues.append("Missing clear Skills section.")
    return issues


def _section_completeness(resume_text: str) -> tuple[int, list[str]]:
    required = ["summary", "skills", "experience", "education"]
    weak = []
    lowered = resume_text.lower()
    for section in required:
        if section not in lowered:
            weak.append(section.title())
    score = round((len(required) - len(weak)) / len(required) * 100)
    return score, weak


def _achievement_score(resume_text: str) -> int:
    bullets = re.findall(r"(^|\n)\s*[-*]\s+(.+)", resume_text)
    if not bullets:
        return 35
    impact = 0
    for _, bullet in bullets:
        if re.search(r"\d|%|\$|improved|reduced|increased|saved|optimized|delivered", bullet, re.I):
            impact += 1
    return round(min(1, impact / max(1, len(bullets))) * 100)


def _experience_score(resume_text: str, job_text: str) -> int:
    resume_lower = resume_text.lower()
    job_terms = [term for term in important_terms(job_text, limit=12) if len(term) > 4]
    matches = [term for term in job_terms if term in resume_lower]
    base = len(matches) / len(job_terms) * 70 if job_terms else 45
    if re.search(r"\b[2-9]\+?\s+years?\b", resume_lower):
        base += 15
    if "project" in resume_lower or "experience" in resume_lower:
        base += 15
    return max(0, min(100, round(base)))


def _role_score(resume_text: str, job_title: str) -> int:
    if not job_title:
        return 70
    title_terms = [term for term in re.findall(r"[a-zA-Z]+", job_title.lower()) if len(term) > 2]
    if not title_terms:
        return 70
    matches = [term for term in title_terms if term in resume_text.lower()]
    return round(len(matches) / len(title_terms) * 100)


def _confidence(score_inputs: dict[str, int], job_text: str, resume_text: str) -> str:
    if len(job_text.split()) > 180 and len(resume_text.split()) > 150:
        return "High"
    if len(job_text.split()) > 80 and len(resume_text.split()) > 80:
        return "Medium"
    return "Low"


def predict_ats_score(resume_text: str, job_details: dict[str, Any] | str) -> dict[str, Any]:
    """Return a weighted, explainable ATS Prediction Score."""

    job_text = _text_from_job(job_details)
    job_skills = extract_known_skills(job_text)
    resume_skills = extract_known_skills(resume_text)
    matched_keywords = sorted(skill for skill in job_skills if skill in resume_skills)
    missing_keywords = sorted(skill for skill in job_skills if skill not in resume_skills)

    skill_match = round(len(matched_keywords) / len(job_skills) * 100) if job_skills else 70
    experience_match = _experience_score(resume_text, job_text)
    keywords = important_terms(job_text, limit=20)
    keyword_matches = [term for term in keywords if term in resume_text.lower()]
    keyword_context = round(len(keyword_matches) / len(keywords) * 100) if keywords else 70
    role_title = _role_score(resume_text, _job_title(job_details))
    section_completeness, weak_sections = _section_completeness(resume_text)
    formatting_issues = _formatting_issues(resume_text)
    formatting = max(0, 100 - len(formatting_issues) * 20)
    achievement = _achievement_score(resume_text)
    critical_missing = [
        skill for skill in missing_keywords if re.search(rf"\b(required|must have|need).{{0,80}}{re.escape(skill)}", job_text, re.I)
    ]
    critical_penalty_score = 100 if not critical_missing else max(0, 100 - len(critical_missing) * 25)

    components = {
        "skill_match": skill_match,
        "experience_match": experience_match,
        "keyword_context": keyword_context,
        "role_title_match": role_title,
        "resume_section_completeness": section_completeness,
        "ats_formatting_check": formatting,
        "achievement_impact_score": achievement,
        "critical_missing_requirement_penalty": critical_penalty_score,
    }
    score = round(
        components["skill_match"] * 0.30
        + components["experience_match"] * 0.15
        + components["keyword_context"] * 0.15
        + components["role_title_match"] * 0.10
        + components["resume_section_completeness"] * 0.10
        + components["ats_formatting_check"] * 0.10
        + components["achievement_impact_score"] * 0.05
        + components["critical_missing_requirement_penalty"] * 0.05
    )
    return {
        "label": "ATS Prediction Score",
        "score": max(0, min(100, score)),
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "weak_resume_sections": weak_sections,
        "formatting_issues": formatting_issues,
        "confidence_level": _confidence(components, job_text, resume_text),
        "components": components,
        "critical_missing_requirements": critical_missing,
    }


def generate_resume_suggestions(
    resume_text: str,
    job_details: dict[str, Any] | str,
) -> list[dict[str, Any]]:
    """Suggest reviewable resume edits without applying them automatically."""

    prediction = predict_ats_score(resume_text, job_details)
    sections = _sections(resume_text)
    missing = prediction["missing_keywords"]
    suggestions: list[ResumeSuggestion] = []
    if missing:
        current = sections.get("skills", "")
        added = missing[:10]
        suggested = (current + "\n" if current else "") + "Relevant keywords to add if truthful: " + ", ".join(added)
        suggestions.append(
            ResumeSuggestion(
                id="skills-keywords",
                section_name="Skills",
                current_text=current,
                suggested_text=suggested.strip(),
                reason_for_change="Adds missing job-description keywords only if they match real experience.",
                keywords_added=added,
            )
        )
    if "Summary" in prediction["weak_resume_sections"] or missing:
        current = sections.get("summary", "")
        role = _job_title(job_details) or "target role"
        suggested = (
            f"IT professional aligned with {role} requirements, with experience across "
            f"{', '.join((prediction['matched_keywords'] + missing)[:8]) or 'technical delivery, collaboration, and problem solving'}."
        )
        suggestions.append(
            ResumeSuggestion(
                id="summary-alignment",
                section_name="Summary",
                current_text=current,
                suggested_text=suggested,
                reason_for_change="Creates a concise tailored summary using job and resume keywords.",
                keywords_added=[keyword for keyword in missing[:6] if keyword in suggested.lower()],
            )
        )
    if prediction["components"]["achievement_impact_score"] < 60:
        current = sections.get("experience", "")
        suggested = (
            current
            + "\n- Add measurable outcomes such as improved reliability, reduced processing time, increased accuracy, or delivered stakeholder impact."
        ).strip()
        suggestions.append(
            ResumeSuggestion(
                id="experience-impact",
                section_name="Experience",
                current_text=current,
                suggested_text=suggested,
                reason_for_change="Improves achievement/impact score by encouraging measurable results.",
                keywords_added=[],
            )
        )
    return [suggestion.to_dict() for suggestion in suggestions]


def apply_approved_suggestions(
    resume_text: str,
    approved_suggestions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate optimized resume text from user-approved suggestions."""

    optimized = resume_text.rstrip()
    keywords_added: list[str] = []
    for suggestion in approved_suggestions:
        section = str(suggestion.get("section_name", "Resume")).strip() or "Resume"
        suggested_text = str(suggestion.get("suggested_text", "")).strip()
        if not suggested_text:
            continue
        optimized += f"\n\n## Approved {section} Update\n{suggested_text}"
        keywords_added.extend(str(item) for item in suggestion.get("keywords_added", []))
    return {
        "optimized_resume": optimized.strip() + "\n",
        "keywords_added": sorted(set(keyword.lower() for keyword in keywords_added if keyword)),
    }


def analyze_resume_workflow(resume_text: str, job_details: dict[str, Any] | str) -> dict[str, Any]:
    before = predict_ats_score(resume_text, job_details)
    suggestions = generate_resume_suggestions(resume_text, job_details)
    return {
        "before": before,
        "suggestions": suggestions,
        "missing_keywords": before["missing_keywords"],
        "weak_resume_sections": before["weak_resume_sections"],
    }
