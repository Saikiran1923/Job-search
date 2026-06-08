"""Application tracking and duplicate detection."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import re

from .models import GeneratedApplication, JobPosting


def _normalize_key_part(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def application_key(job: JobPosting, allow_reposts: bool = False) -> str:
    """Return the duplicate-detection key.

    By default, the assistant blocks the same role at the same company.
    If repost handling is enabled, the URL is included so a repost or distinct listing can proceed.
    """

    parts = [_normalize_key_part(job.company), _normalize_key_part(job.role)]
    if allow_reposts:
        parts.append(_normalize_key_part(job.url))
    return "::".join(parts)


class ApplicationStore:
    """JSONL-backed application tracking store."""

    def __init__(self, path: Path, allow_reposts: bool = False) -> None:
        self.path = path
        self.allow_reposts = allow_reposts
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    records.append(json.loads(stripped))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL record at {self.path}:{line_number}") from exc
        return records

    def has_seen(self, job: JobPosting) -> bool:
        key = application_key(job, allow_reposts=self.allow_reposts)
        return any(record.get("dedupe_key") == key for record in self._records())

    def append(self, application: GeneratedApplication) -> None:
        analysis = application.analysis
        record = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "dedupe_key": application_key(analysis.job, allow_reposts=self.allow_reposts),
            "job_role": analysis.job.role,
            "job_title": analysis.job.title,
            "company_name": analysis.job.company,
            "job_url": analysis.job.url,
            "source": analysis.job.source,
            "location": analysis.job.location,
            "ats_score": analysis.ats_score,
            "matched_skills": analysis.matched_skills,
            "missing_skills": analysis.missing_skills,
            "important_keywords": analysis.important_keywords,
            "selected_bullets": analysis.selected_bullets,
            "resume_used": str(application.resume_path),
            "cover_letter_used": str(application.cover_letter_path),
            "application_status": application.status,
            "decision_reason": analysis.decision_reason,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self._records():
            status = str(record.get("application_status", "unknown"))
            counts[status] = counts.get(status, 0) + 1
        return counts
