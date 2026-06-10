"""ATS scoring and bullet selection logic."""

from __future__ import annotations

from .keywords import extract_known_skills, important_terms, normalize_text
from .models import CandidateProfile, JobAnalysis, JobPosting, RoleLibrary


def _contains_term(text: str, term: str) -> bool:
    return normalize_text(term) in normalize_text(text)


def _score_text(text: str, job_skills: list[str], keyword_candidates: list[str]) -> int:
    skills = set(extract_known_skills(text))
    matched_skills = [skill for skill in job_skills if skill.lower() in skills]
    skill_score = len(matched_skills) / len(job_skills) if job_skills else 0.75
    keyword_matches = [term for term in keyword_candidates if _contains_term(text, term)]
    keyword_score = len(keyword_matches) / len(keyword_candidates) if keyword_candidates else 0.75
    return max(0, min(100, round((skill_score * 0.7 + keyword_score * 0.3) * 100)))


def select_role_bullets(
    role_library: RoleLibrary,
    job_text: str,
    missing_skills: list[str],
    limit: int = 4,
) -> list[str]:
    """Select role bullets that address job keywords and missing skills."""

    if not role_library.bullets:
        return []

    job_terms = set(extract_known_skills(job_text)) | set(important_terms(job_text, limit=30))
    missing = {term.lower() for term in missing_skills}
    scored: list[tuple[int, str]] = []
    for bullet in role_library.bullets:
        bullet_text = bullet.text.lower()
        bullet_keywords = {item.lower() for item in bullet.keywords}
        score = 0
        score += sum(4 for term in missing if term in bullet_text or term in bullet_keywords)
        score += sum(2 for term in job_terms if term in bullet_text or term in bullet_keywords)
        if score:
            scored.append((score, bullet.text))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [text for _, text in scored[:limit]]


def score_job(
    profile: CandidateProfile,
    job: JobPosting,
    role_library: RoleLibrary,
    threshold: int = 85,
    suggested_answers: dict[str, str] | None = None,
) -> JobAnalysis:
    """Compare the job description with the candidate profile and return a score."""

    profile_text = profile.resume_text()
    job_text = "\n".join([job.role, job.title, job.description])
    job_skills = extract_known_skills(job_text)
    keyword_candidates = important_terms(job_text, limit=20)
    profile_skills = extract_known_skills(profile_text) + list(profile.all_skill_terms())
    profile_skill_set = {skill.lower() for skill in profile_skills}

    matched_skills = sorted(skill for skill in job_skills if skill.lower() in profile_skill_set)
    missing_skills = sorted(skill for skill in job_skills if skill.lower() not in profile_skill_set)
    selected_bullets = select_role_bullets(role_library, job_text, missing_skills)

    optimized_text = "\n".join([profile_text, *selected_bullets])
    original_score = _score_text(profile_text, job_skills, keyword_candidates)
    score = _score_text(optimized_text, job_skills, keyword_candidates)

    if score >= threshold:
        decision = "prepare"
        reason = f"ATS score {score}% meets threshold {threshold}%."
    elif selected_bullets:
        decision = "review"
        reason = (
            f"ATS score {score}% remains below {threshold}% after tailoring; "
            "review truthfulness before applying."
        )
    else:
        decision = "skip"
        reason = f"ATS score {score}% is below threshold {threshold}% and no relevant bullets were found."

    return JobAnalysis(
        job=job,
        ats_score=score,
        original_ats_score=original_score,
        optimized_ats_score=score,
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        important_keywords=keyword_candidates,
        selected_bullets=selected_bullets,
        suggested_answers=suggested_answers or {},
        decision=decision,
        decision_reason=reason,
    )
