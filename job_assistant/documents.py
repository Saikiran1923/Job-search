"""Resume and cover-letter generation."""

from __future__ import annotations

from pathlib import Path
import re

from .models import CandidateProfile, JobAnalysis


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug or "application"


def _contact_line(profile: CandidateProfile) -> str:
    parts = [profile.location, profile.email, profile.phone, *profile.links]
    return " | ".join(part for part in parts if part)


def render_resume(profile: CandidateProfile, analysis: JobAnalysis) -> str:
    """Render an ATS-friendly tailored resume in Markdown."""

    lines: list[str] = [
        f"# {profile.name}",
        _contact_line(profile),
        "",
        f"## Target Role: {analysis.job.title}",
        "",
        "## Professional Summary",
        profile.summary,
        "",
        "## Key Skills",
    ]
    for category, skills in profile.skills.items():
        if skills:
            lines.append(f"- **{category}:** {', '.join(skills)}")

    if analysis.selected_bullets:
        lines.extend(["", "## Tailored Role Highlights"])
        lines.extend(f"- {bullet}" for bullet in analysis.selected_bullets)

    lines.extend(["", "## Professional Experience"])
    for exp in profile.experience:
        title_line = " - ".join(part for part in [exp.title, exp.company, exp.dates] if part)
        lines.append(f"### {title_line}")
        lines.extend(f"- {bullet}" for bullet in exp.bullets)
        lines.append("")

    if profile.education:
        lines.append("## Education")
        for edu in profile.education:
            edu_line = " - ".join(part for part in [edu.degree, edu.institution, edu.dates] if part)
            lines.append(f"- {edu_line}")

    if profile.certifications:
        lines.extend(["", "## Certifications"])
        lines.extend(f"- {certification}" for certification in profile.certifications)

    lines.extend(
        [
            "",
            "## ATS Alignment Notes",
            f"- Original resume ATS match score: {analysis.original_ats_score}%",
            f"- Optimized resume ATS match score: {analysis.optimized_ats_score}%",
            f"- Matched skills: {', '.join(analysis.matched_skills) or 'None detected'}",
            f"- Missing or review-required skills: {', '.join(analysis.missing_skills) or 'None detected'}",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def render_cover_letter(profile: CandidateProfile, analysis: JobAnalysis) -> str:
    """Render a concise customized cover letter in Markdown."""

    company = analysis.job.company
    role = analysis.job.title
    highlights = analysis.selected_bullets[:3]
    if not highlights:
        highlights = [bullet for exp in profile.experience for bullet in exp.bullets[:1]][:3]

    lines = [
        f"# Cover Letter - {profile.name}",
        "",
        f"Dear {company} Hiring Team,",
        "",
        (
            f"I am excited to apply for the {role} role at {company}. "
            f"My background aligns with the requirements in your posting, especially around "
            f"{', '.join(analysis.matched_skills[:6]) or 'the technical and delivery priorities described'}."
        ),
        "",
    ]
    if highlights:
        lines.append("A few relevant strengths I would bring include:")
        lines.extend(f"- {highlight}" for highlight in highlights)
        lines.append("")
    lines.extend(
        [
            (
                "I would welcome the opportunity to discuss how my experience can help your team "
                "deliver reliable, measurable technology outcomes."
            ),
            "",
            "Sincerely,",
            profile.name,
        ]
    )
    return "\n".join(lines).strip() + "\n"


def write_application_documents(
    profile: CandidateProfile,
    analysis: JobAnalysis,
    output_dir: Path,
) -> tuple[Path, Path]:
    """Write tailored resume and cover letter files for a job."""

    folder = output_dir / safe_slug(f"{analysis.job.company}-{analysis.job.role}")
    folder.mkdir(parents=True, exist_ok=True)
    resume_path = folder / "resume.md"
    cover_letter_path = folder / "cover_letter.md"
    resume_path.write_text(render_resume(profile, analysis), encoding="utf-8")
    cover_letter_path.write_text(render_cover_letter(profile, analysis), encoding="utf-8")
    return resume_path, cover_letter_path
