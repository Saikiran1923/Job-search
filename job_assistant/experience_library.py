"""Experience point library lookup and employer-preserved placement."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import re


DEFAULT_LIBRARY_DIR = Path("experience_points_library")


def normalize_skill(value: str) -> str:
    value = value.lower().replace("sap idocs", "idoc").replace("idocs", "idoc")
    value = value.replace("s/4hana", "s4hana")
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def _load_points(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    points = data.get("points", [])
    return [point for point in points if isinstance(point, dict) and point.get("point")]


def search_experience_points(
    missing_skills: list[str],
    library_dir: Path = DEFAULT_LIBRARY_DIR,
) -> dict[str, list[dict[str, Any]]]:
    """Return matching library points for each missing skill."""

    results: dict[str, list[dict[str, Any]]] = {}
    if not library_dir.exists():
        return {skill: [] for skill in missing_skills}

    files = list(library_dir.glob("*/*.json"))
    for skill in missing_skills:
        normalized = normalize_skill(skill)
        tokens = {token for token in normalized.split("_") if token}
        matches: list[dict[str, Any]] = []
        for path in files:
            file_key = normalize_skill(path.stem)
            file_tokens = {token for token in file_key.split("_") if token}
            if normalized == file_key or tokens & file_tokens:
                matches.extend(_load_points(path))
                continue
            for point in _load_points(path):
                haystack = normalize_skill(" ".join(str(point.get(field, "")) for field in ["skill", "point", "project", "role"]))
                if normalized in haystack or any(token in haystack for token in tokens):
                    matches.append(point)
        deduped = {}
        for point in matches:
            key = (point.get("employer"), point.get("project"), point.get("role"), point.get("point"))
            deduped[key] = point
        results[skill] = sorted(
            deduped.values(),
            key=lambda item: int(item.get("confidence_score", 0)),
            reverse=True,
        )
    return results


def group_points_by_employer(approved_points: list[dict[str, Any]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Group approved points without moving them between employers/projects."""

    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for point in approved_points:
        employer = str(point.get("employer", "Unknown Employer"))
        project = str(point.get("project", "General"))
        grouped.setdefault(employer, {}).setdefault(project, []).append(point)
    return grouped


def render_employer_placed_points(approved_points: list[dict[str, Any]]) -> str:
    grouped = group_points_by_employer(approved_points)
    lines: list[str] = []
    for employer, projects in grouped.items():
        lines.append(f"## {employer}")
        for project, points in projects.items():
            lines.append(f"### {project}")
            for point in points:
                lines.append(f"- {point.get('point', '')}")
            lines.append("")
    return "\n".join(lines).strip()
