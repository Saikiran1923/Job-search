"""Data models and JSON loading helpers for the assistant."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json


class ConfigError(ValueError):
    """Raised when input configuration cannot be loaded or validated."""


def _read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc


def _string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{field_name} must be a list of strings")
    return value


@dataclass(frozen=True)
class Experience:
    title: str
    company: str
    dates: str
    bullets: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Experience":
        return cls(
            title=str(value.get("title", "")).strip(),
            company=str(value.get("company", "")).strip(),
            dates=str(value.get("dates", "")).strip(),
            bullets=_string_list(value.get("bullets", []), "experience.bullets"),
        )


@dataclass(frozen=True)
class Education:
    institution: str
    degree: str
    dates: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Education":
        return cls(
            institution=str(value.get("institution", "")).strip(),
            degree=str(value.get("degree", "")).strip(),
            dates=str(value.get("dates", "")).strip(),
        )


@dataclass(frozen=True)
class CandidateProfile:
    name: str
    email: str = ""
    phone: str = ""
    location: str = ""
    links: list[str] = field(default_factory=list)
    summary: str = ""
    skills: dict[str, list[str]] = field(default_factory=dict)
    experience: list[Experience] = field(default_factory=list)
    education: list[Education] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)

    @classmethod
    def from_path(cls, path: Path) -> "CandidateProfile":
        data = _read_json(path)
        if not isinstance(data, dict):
            raise ConfigError("Candidate profile must be a JSON object")
        name = str(data.get("name", "")).strip()
        if not name:
            raise ConfigError("Candidate profile requires a non-empty name")
        raw_skills = data.get("skills", {})
        if not isinstance(raw_skills, dict):
            raise ConfigError("skills must be an object of category -> list[str]")
        skills = {
            str(category): _string_list(values, f"skills.{category}")
            for category, values in raw_skills.items()
        }
        return cls(
            name=name,
            email=str(data.get("email", "")).strip(),
            phone=str(data.get("phone", "")).strip(),
            location=str(data.get("location", "")).strip(),
            links=_string_list(data.get("links", []), "links"),
            summary=str(data.get("summary", "")).strip(),
            skills=skills,
            experience=[Experience.from_dict(item) for item in data.get("experience", [])],
            education=[Education.from_dict(item) for item in data.get("education", [])],
            certifications=_string_list(data.get("certifications", []), "certifications"),
        )

    def all_skill_terms(self) -> set[str]:
        terms: set[str] = set()
        for values in self.skills.values():
            terms.update(item.strip().lower() for item in values if item.strip())
        return terms

    def resume_text(self) -> str:
        parts: list[str] = [
            self.name,
            self.summary,
            " ".join(self.links),
            " ".join(self.certifications),
        ]
        for values in self.skills.values():
            parts.extend(values)
        for item in self.experience:
            parts.extend([item.title, item.company, item.dates, *item.bullets])
        for item in self.education:
            parts.extend([item.institution, item.degree, item.dates])
        return "\n".join(part for part in parts if part)


@dataclass(frozen=True)
class JobPosting:
    role: str
    company: str
    title: str
    url: str
    source: str = ""
    location: str = ""
    description: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "JobPosting":
        role = str(value.get("role", "")).strip()
        company = str(value.get("company", "")).strip()
        title = str(value.get("title", role)).strip()
        url = str(value.get("url", "")).strip()
        description = str(value.get("description", "")).strip()
        if not role:
            raise ConfigError("Each job requires a role")
        if not company:
            raise ConfigError(f"Job '{role}' requires a company")
        if not url:
            raise ConfigError(f"Job '{role}' at '{company}' requires a url")
        if not description:
            raise ConfigError(f"Job '{role}' at '{company}' requires a description")
        return cls(
            role=role,
            company=company,
            title=title or role,
            url=url,
            source=str(value.get("source", "")).strip(),
            location=str(value.get("location", "")).strip(),
            description=description,
        )


def load_jobs(path: Path) -> list[JobPosting]:
    data = _read_json(path)
    if isinstance(data, dict):
        data = data.get("jobs", [])
    if not isinstance(data, list):
        raise ConfigError("Jobs file must be a list or an object with a jobs list")
    return [JobPosting.from_dict(item) for item in data]


@dataclass(frozen=True)
class RoleBullet:
    text: str
    keywords: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | str) -> "RoleBullet":
        if isinstance(value, str):
            return cls(text=value)
        return cls(
            text=str(value.get("text", "")).strip(),
            keywords=_string_list(value.get("keywords", []), "role bullet keywords"),
        )


@dataclass(frozen=True)
class RoleLibrary:
    role: str
    bullets: list[RoleBullet]

    @classmethod
    def from_path(cls, path: Path, role: str) -> "RoleLibrary":
        if not path.exists():
            return cls(role=role, bullets=[])
        data = _read_json(path)
        if not isinstance(data, dict):
            raise ConfigError(f"Role library must be a JSON object: {path}")
        bullets = [RoleBullet.from_dict(item) for item in data.get("bullets", [])]
        return cls(role=str(data.get("role", role)), bullets=[item for item in bullets if item.text])


@dataclass(frozen=True)
class JobAnalysis:
    job: JobPosting
    ats_score: int
    matched_skills: list[str]
    missing_skills: list[str]
    important_keywords: list[str]
    selected_bullets: list[str]
    decision: str
    decision_reason: str


@dataclass(frozen=True)
class GeneratedApplication:
    analysis: JobAnalysis
    resume_path: Path
    cover_letter_path: Path
    status: str
