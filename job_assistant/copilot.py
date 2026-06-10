"""Manual-controlled Job Application Copilot workflow."""

from __future__ import annotations

from typing import Any
import re

from .ats_prediction import analyze_resume_workflow, apply_approved_suggestions, predict_ats_score
from .autofill import build_application_assist
from .interview import generate_interview_prep
from .job_extractor import (
    JD_INCOMPLETE,
    JD_INCOMPLETE_MESSAGE,
    JOB_ACTIVE,
    JOB_CLOSED,
    JOB_CLOSED_MESSAGE,
    LOGIN_REQUIRED,
    LOGIN_REQUIRED_MESSAGE,
    MANUAL_JD_REQUIRED,
    PAGE_ACCESSIBLE,
    extract_job_from_url,
)
from .portal_sessions import detect_portal


PIPELINE_STEPS = [
    "Extract Job Details",
    "Validate JD",
    "ATS Before Score",
    "Resume Suggestions",
    "ATS After Score",
    "Interview Questions",
    "Application Assist",
    "Save Tracker",
]


def pending_statuses() -> dict[str, str]:
    return {step: "Pending" for step in PIPELINE_STEPS}


def validate_job_details(job_details: dict[str, Any]) -> tuple[bool, str]:
    intake_status = str(job_details.get("intake_status", ""))
    if intake_status == LOGIN_REQUIRED:
        return False, LOGIN_REQUIRED_MESSAGE
    if intake_status == JOB_CLOSED:
        return False, JOB_CLOSED_MESSAGE
    if intake_status in {JD_INCOMPLETE, MANUAL_JD_REQUIRED}:
        return False, JD_INCOMPLETE_MESSAGE

    title = str(job_details.get("job_title", "")).strip().lower()
    description = str(job_details.get("full_job_description", "")).strip()
    text = f"{title}\n{description}".lower()
    invalid_titles = {"login", "sign in", "signin", "join", "jobs", "careers"}
    if title in invalid_titles:
        return False, LOGIN_REQUIRED_MESSAGE
    if "the job you are trying to apply for has been filled" in text or "no longer available" in text:
        return False, JOB_CLOSED_MESSAGE
    if len(description.split()) < 45:
        return False, JD_INCOMPLETE_MESSAGE
    sign_in_words = ["sign in", "join now", "forgot password", "create account", "login"]
    if sum(1 for word in sign_in_words if word in text) >= 2 and len(description.split()) < 120:
        return False, LOGIN_REQUIRED_MESSAGE
    return True, ""


def job_details_from_manual_jd(
    job_description: str,
    job_url: str = "",
    job_title: str = "Manual Job",
    company_name: str = "",
) -> dict[str, Any]:
    from .keywords import extract_known_skills

    skills = extract_known_skills(job_description)
    return {
        "success": True,
        "intake_status": JOB_ACTIVE,
        "message": "",
        "next_action": "Continue ATS workflow automatically.",
        "job_title": job_title,
        "company_name": company_name,
        "job_url": job_url,
        "source": detect_portal(job_url) if job_url else "manual",
        "location": "",
        "work_mode": "",
        "employment_type": "",
        "salary_range": "",
        "full_job_description": job_description,
        "responsibilities": _section_lines(job_description, ["responsibilities", "what you will do"]),
        "required_qualifications": _section_lines(job_description, ["requirements", "required qualifications"]),
        "preferred_qualifications": _section_lines(job_description, ["preferred qualifications", "preferred"]),
        "required_skills": skills,
        "preferred_skills": [],
        "benefits": _section_lines(job_description, ["benefits", "perks"]),
        "visible_application_questions": _visible_questions(job_description),
    }


def run_manual_pipeline(
    db: Any,
    user_id: int,
    job_details: dict[str, Any],
    resume_text: str,
    auto_run_after_intake: bool = True,
) -> dict[str, Any]:
    statuses = pending_statuses()
    statuses["Extract Job Details"] = str(job_details.get("intake_status") or JOB_ACTIVE)

    valid, validation_error = validate_job_details(job_details)
    statuses["Validate JD"] = "Completed" if valid else str(job_details.get("intake_status") or MANUAL_JD_REQUIRED)
    if not valid:
        job_details = {
            **job_details,
            "message": job_details.get("message") or validation_error,
            "next_action": job_details.get("next_action") or "Paste the JD manually or upload a JD file.",
        }
        return db.create_pipeline_run(
            user_id,
            {
                "job_url": job_details.get("job_url", ""),
                "job_details": job_details,
                "resume_text": resume_text,
                "statuses": statuses,
            },
        )

    workflow = analyze_resume_workflow(resume_text, job_details)
    statuses["ATS Before Score"] = "Completed"
    statuses["Resume Suggestions"] = "Completed"
    statuses["ATS After Score"] = "Pending"
    questions = generate_interview_prep(
        optimized_resume=resume_text,
        job_description=str(job_details.get("full_job_description", "")),
        role=str(job_details.get("job_title", "IT Role")),
    )
    flat_questions = [*questions["level_1"], *questions["level_2"]]
    db.save_interview_questions(user_id, flat_questions)
    statuses["Interview Questions"] = "Completed"

    visible_questions = list(job_details.get("visible_application_questions") or [])
    if visible_questions:
        db.save_unanswered_questions(
            user_id,
            visible_questions,
            company_name=str(job_details.get("company_name", "")),
            job_title=str(job_details.get("job_title", "")),
            job_url=str(job_details.get("job_url", "")),
        )
    answer_lookup = {}
    for question in visible_questions:
        match = db.find_answer_for_question(user_id, str(question.get("question", "")))
        if match:
            answer_lookup[str(question.get("question", ""))] = match["answer"]
    assist = build_application_assist(db.get_profile(user_id), visible_questions, answer_lookup)
    statuses["Application Assist"] = "Completed"

    app = db.create_application(
        user_id,
        {
            "role": job_details.get("job_title", "Manual Job"),
            "title": job_details.get("job_title", "Manual Job"),
            "company": job_details.get("company_name", "Unknown Company"),
            "url": job_details.get("job_url", ""),
            "source": job_details.get("source", ""),
            "location": job_details.get("location", ""),
            "work_mode": job_details.get("work_mode", ""),
            "employment_type": job_details.get("employment_type", ""),
            "salary_range": job_details.get("salary_range", ""),
            "status": "saved",
            "original_ats_score": workflow["before"]["score"],
            "optimized_ats_score": 0,
            "ats_improvement": 0,
            "missing_skills": workflow["before"]["missing_keywords"],
            "unanswered_questions_count": len(assist["unanswered_questions_found"]),
            "interview_questions_generated": len(flat_questions),
            "notes": "Created by manual copilot pipeline; user must review and submit manually.",
        },
    )
    statuses["Save Tracker"] = "Completed"
    return db.create_pipeline_run(
        user_id,
        {
            "job_url": job_details.get("job_url", ""),
            "job_details": job_details,
            "resume_text": resume_text,
            "statuses": statuses,
            "ats_before": workflow["before"]["score"],
            "suggestions": workflow["suggestions"],
            "application_assist": assist,
            "application_id": app["id"],
        },
    )


def complete_resume_approval(
    db: Any,
    user_id: int,
    resume_text: str,
    job_details: dict[str, Any],
    approved_suggestions: list[dict[str, Any]],
    application_id: int | None = None,
) -> dict[str, Any]:
    before = predict_ats_score(resume_text, job_details)
    optimized = apply_approved_suggestions(resume_text, approved_suggestions)
    after = predict_ats_score(optimized["optimized_resume"], job_details)
    version = db.create_resume_version(
        user_id,
        {
            "application_id": application_id,
            "original_resume": resume_text,
            "optimized_resume": optimized["optimized_resume"],
            "job_title": job_details.get("job_title", ""),
            "company": job_details.get("company_name", ""),
            "job_url": job_details.get("job_url", ""),
            "ats_before": before["score"],
            "ats_after": after["score"],
            "keywords_added": optimized["keywords_added"],
        },
    )
    if application_id:
        db.update_application(
            user_id,
            application_id,
            {
                "optimized_ats_score": after["score"],
                "ats_improvement": after["score"] - before["score"],
                "resume_version": version["label"],
            },
        )
    return {
        "before": before,
        "after": after,
        "improvement_percentage": after["score"] - before["score"],
        "optimized_resume": optimized["optimized_resume"],
        "keywords_added": optimized["keywords_added"],
        "resume_version": version,
    }


def extract_or_manual_job(job_url: str = "", manual_jd: str = "", **metadata: str) -> dict[str, Any]:
    if job_url:
        extracted = extract_job_from_url(job_url)
        if extracted.get("success"):
            return extracted
        if not manual_jd:
            return extracted
    if manual_jd:
        return job_details_from_manual_jd(
            manual_jd,
            job_url=job_url,
            job_title=metadata.get("job_title") or "Manual Job",
            company_name=metadata.get("company_name") or "",
        )
    return {
        "success": False,
        "intake_status": MANUAL_JD_REQUIRED,
        "message": JD_INCOMPLETE_MESSAGE,
        "next_action": "Paste the JD manually or upload a JD file.",
        "job_url": job_url,
        "source": detect_portal(job_url),
    }


def _section_lines(text: str, headings: list[str]) -> list[str]:
    lowered = text.lower()
    for heading in headings:
        idx = lowered.find(heading)
        if idx >= 0:
            chunk = text[idx : idx + 1200]
            return [line.strip(" -•\t") for line in re.split(r"\n|•|- ", chunk) if len(line.strip()) > 6][:8]
    return []


def _visible_questions(text: str) -> list[dict[str, object]]:
    questions = []
    for match in re.finditer(r"([^.\n?!]{10,160}\?)", text):
        questions.append({"question": re.sub(r"\s+", " ", match.group(1)).strip(), "options": []})
    return questions[:20]
