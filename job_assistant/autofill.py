"""Review-only autofill draft generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import CandidateProfile, ConfigError


def _load_profile(profile_path: Path = Path("data/candidate_profile.json")) -> CandidateProfile | None:
    try:
        return CandidateProfile.from_path(profile_path)
    except ConfigError:
        fallback = Path("data/candidate_profile.example.json")
        try:
            return CandidateProfile.from_path(fallback)
        except ConfigError:
            return None


def profile_autofill_fields(profile: CandidateProfile | None) -> dict[str, str]:
    if not profile:
        return {}
    fields = {
        "name": profile.name,
        "email": profile.email,
        "phone": profile.phone,
        "address": profile.location,
        "linkedin": "",
        "portfolio": "",
        "education": "; ".join(
            " - ".join(part for part in [edu.degree, edu.institution, edu.dates] if part)
            for edu in profile.education
        ),
        "experience": "; ".join(
            " - ".join(part for part in [exp.title, exp.company, exp.dates] if part)
            for exp in profile.experience
        ),
    }
    for link in profile.links:
        lowered = link.lower()
        if "linkedin" in lowered:
            fields["linkedin"] = link
        elif not fields["portfolio"]:
            fields["portfolio"] = link
    return fields


def build_autofill_draft(
    questions: list[dict[str, Any]],
    answer_lookup: dict[str, str],
    profile_path: Path = Path("data/candidate_profile.json"),
) -> dict[str, Any]:
    """Build a user-reviewable autofill draft. This does not submit forms."""

    profile = _load_profile(profile_path)
    fields = profile_autofill_fields(profile)
    saved_answers = []
    unanswered = []
    for question in questions:
        text = str(question.get("question", "")).strip()
        if not text:
            continue
        answer = answer_lookup.get(text)
        if answer:
            saved_answers.append({"question": text, "answer": answer, "options": question.get("options", [])})
        else:
            unanswered.append({"question": text, "options": question.get("options", [])})

    return {
        "mode": "review_only",
        "safety_note": "Autofill assistant prepares fields only. User reviews, uploads resume, solves CAPTCHA, and submits manually.",
        "profile_fields": fields,
        "saved_answers": saved_answers,
        "unanswered_questions": unanswered,
        "stop_before_final_submission": True,
    }


def build_application_assist(
    profile: dict[str, Any],
    questions: list[dict[str, Any]],
    answer_lookup: dict[str, str],
) -> dict[str, Any]:
    """Build review-only application field suggestions from saved profile data."""

    field_map = {
        "first_name": profile.get("first_name", ""),
        "last_name": profile.get("last_name", ""),
        "email": profile.get("email", ""),
        "phone": profile.get("phone", ""),
        "address": profile.get("address", ""),
        "city": profile.get("city", ""),
        "state": profile.get("state", ""),
        "zip": profile.get("zip", ""),
        "country": profile.get("country", ""),
        "linkedin": profile.get("linkedin_url", ""),
        "portfolio": profile.get("portfolio_url", ""),
        "github": profile.get("github_url", ""),
        "education": profile.get("education", ""),
        "experience": profile.get("total_experience", ""),
        "work_authorization": profile.get("work_authorization", ""),
        "sponsorship_answer": profile.get("sponsorship_required", ""),
        "relocation_preference": profile.get("relocation_preference", ""),
        "work_mode_preference": profile.get("work_mode_preference", ""),
    }
    missing = [field for field, value in field_map.items() if not str(value).strip()]
    saved_answers = []
    unanswered = []
    for question in questions:
        text = str(question.get("question", "")).strip()
        if not text:
            continue
        if text in answer_lookup:
            saved_answers.append({"question": text, "answer": answer_lookup[text], "options": question.get("options", [])})
        else:
            unanswered.append({"question": text, "options": question.get("options", [])})
    return {
        "mode": "review_only",
        "safety_note": "Application Assist suggests fields only. User reviews, uploads final resume, solves CAPTCHA, and submits manually.",
        "profile_fields_ready": {field: value for field, value in field_map.items() if str(value).strip()},
        "missing_profile_fields": missing,
        "saved_answers_found": saved_answers,
        "unanswered_questions_found": unanswered,
        "stop_before_final_submission": True,
    }
