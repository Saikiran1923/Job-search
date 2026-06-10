"""Role-based experience point library lookup and user-assigned placement."""

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
    loaded = []
    for point in points:
        if isinstance(point, dict) and point.get("point"):
            loaded.append(
                {
                    "skill": str(point.get("skill", "")),
                    "category": str(point.get("category", "")),
                    "point": str(point.get("point", "")),
                    "priority": int(point.get("priority", 99)),
                    "source_file": str(path),
                    "role_folder": path.parent.name,
                }
            )
    return loaded


def search_experience_points(
    missing_skills: list[str],
    library_dir: Path = DEFAULT_LIBRARY_DIR,
    role: str = "",
) -> dict[str, list[dict[str, Any]]]:
    """Return matching library points for each missing skill."""

    results: dict[str, list[dict[str, Any]]] = {}
    if not library_dir.exists():
        return {skill: [] for skill in missing_skills}

    role_key = normalize_skill(role)
    all_files = list(library_dir.glob("*/*.json"))
    role_files = [path for path in all_files if normalize_skill(path.parent.name) == role_key] if role_key else []
    generic_files = [path for path in all_files if path.parent.name == "generic"]
    files = role_files + [path for path in all_files if path not in role_files and path not in generic_files] + generic_files
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
                haystack = normalize_skill(" ".join(str(point.get(field, "")) for field in ["skill", "category", "point", "role_folder"]))
                if normalized in haystack or any(token in haystack for token in tokens):
                    matches.append(point)
        deduped = {}
        for point in matches:
            key = (point.get("skill"), point.get("category"), point.get("point"))
            deduped[key] = point
        results[skill] = sorted(
            deduped.values(),
            key=lambda item: int(item.get("priority", 99)),
        )
    return results


def group_points_by_employer(approved_points: list[dict[str, Any]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Group approved points by user-assigned employer/project."""

    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for point in approved_points:
        employer = str(point.get("assigned_employer", "")).strip()
        project = str(point.get("assigned_project", "")).strip()
        if not employer or not project:
            # Assignment is mandatory; unassigned points are intentionally ignored.
            continue
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
                skill = str(point.get("skill", "")).strip()
                prefix = f"{skill}: " if skill else ""
                lines.append(f"- {prefix}{point.get('point', '')}")
            lines.append("")
    return "\n".join(lines).strip()
