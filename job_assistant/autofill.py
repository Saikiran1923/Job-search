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
