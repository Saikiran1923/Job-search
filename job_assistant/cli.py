"""Command line interface for the job application assistant."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path
import json
import shutil
import sys

from .answers import AnswerBank
from .ats import score_job
from .documents import write_application_documents
from .keywords import ROLE_CATALOG, normalize_role
from .models import (
    CandidateProfile,
    ConfigError,
    GeneratedApplication,
    RoleLibrary,
    load_jobs,
)
from .search import SUPPORTED_PLATFORMS, build_search_links, build_search_plan
from .storage import ApplicationStore


DEFAULT_PROFILE = (
    Path("/data/candidate_profile.json")
    if Path("/data/candidate_profile.json").exists()
    else Path("data/candidate_profile.json")
)
DEFAULT_JOBS = Path("data/jobs/jobs.example.json")
DEFAULT_ROLES_DIR = Path("/data/roles") if Path("/data/roles").exists() else Path("data/roles")
DEFAULT_OUTPUT_DIR = Path("applications")
DEFAULT_TRACKING = Path("applications/applications.jsonl")
DEFAULT_ANSWERS = (
    Path("/data/application_answers.json")
    if Path("/data/application_answers.json").exists()
    else Path("data/application_answers.json")
)


def _load_role_library(roles_dir: Path, role: str) -> RoleLibrary:
    role_path = roles_dir / f"{normalize_role(role)}.json"
    fallback_path = roles_dir / "general_it.json"
    if role_path.exists():
        return RoleLibrary.from_path(role_path, role=role)
    return RoleLibrary.from_path(fallback_path, role=role)


def _cmd_search_links(args: Namespace) -> int:
    links = build_search_links(
        roles=args.roles,
        platforms=args.platforms,
        location=args.location,
        all_it=args.all_it,
        categories=args.categories,
    )
    print(json.dumps(links, indent=2, sort_keys=True))
    return 0


def _cmd_search_plan(args: Namespace) -> int:
    plan = build_search_plan(
        roles=args.roles,
        platforms=args.platforms,
        location=args.location,
        all_it=args.all_it,
        categories=args.categories,
        minimum_review_seconds=args.minimum_review_seconds,
    )
    print(json.dumps({"steps": plan}, indent=2, sort_keys=True))
    return 0


def _cmd_roles(args: Namespace) -> int:
    print(json.dumps(ROLE_CATALOG, indent=2, sort_keys=True))
    return 0


def _cmd_answers_add(args: Namespace) -> int:
    bank = AnswerBank(args.answers)
    bank.add(
        question=args.question,
        answer=args.answer,
        options=args.options,
        keywords=args.keywords,
        replace=args.replace,
    )
    bank.save()
    print(f"Saved answer for: {args.question}")
    return 0


def _cmd_answers_list(args: Namespace) -> int:
    bank = AnswerBank(args.answers)
    print(
        json.dumps(
            [
                {
                    "question": answer.question,
                    "answer": answer.answer,
                    "options": answer.options,
                    "keywords": answer.keywords,
                }
                for answer in bank.answers
            ],
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _cmd_answers_match(args: Namespace) -> int:
    bank = AnswerBank(args.answers)
    match = bank.match(args.question, args.options)
    if not match:
        print(json.dumps({"matched": False, "answer": None}, indent=2))
        return 1
    print(
        json.dumps(
            {
                "matched": True,
                "question": match.question,
                "answer": match.answer,
                "options": match.options,
                "keywords": match.keywords,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _cmd_process(args: Namespace) -> int:
    profile = CandidateProfile.from_path(args.profile)
    jobs = load_jobs(args.jobs)
    store = ApplicationStore(args.tracking, allow_reposts=args.allow_reposts)
    answer_bank = AnswerBank(args.answers)
    results = []

    for job in jobs:
        if store.has_seen(job):
            results.append(
                {
                    "company": job.company,
                    "role": job.role,
                    "status": "skipped_duplicate",
                    "reason": "Same company and role already exists in tracking store.",
                }
            )
            continue

        role_library = _load_role_library(args.roles_dir, job.role)
        suggested_answers = answer_bank.suggestions(
            [(question.question, question.options) for question in job.application_questions]
        )
        analysis = score_job(
            profile,
            job,
            role_library,
            threshold=args.threshold,
            suggested_answers=suggested_answers,
        )

        if analysis.decision == "skip":
            results.append(
                {
                    "company": job.company,
                    "role": job.role,
                    "status": "skipped_low_match",
                    "ats_score": analysis.ats_score,
                    "original_ats_score": analysis.original_ats_score,
                    "optimized_ats_score": analysis.optimized_ats_score,
                    "suggested_answers": suggested_answers,
                    "reason": analysis.decision_reason,
                }
            )
            continue

        resume_path, cover_letter_path = write_application_documents(
            profile,
            analysis,
            args.output_dir,
        )
        status = (
            "prepared_for_manual_submission"
            if analysis.decision == "prepare"
            else "needs_truthfulness_review"
        )
        application = GeneratedApplication(
            analysis=analysis,
            resume_path=resume_path,
            cover_letter_path=cover_letter_path,
            status=status,
        )
        store.append(application)
        results.append(
            {
                "company": job.company,
                "role": job.role,
                "status": status,
                "ats_score": analysis.ats_score,
                "original_ats_score": analysis.original_ats_score,
                "optimized_ats_score": analysis.optimized_ats_score,
                "resume": str(resume_path),
                "cover_letter": str(cover_letter_path),
                "suggested_answers": suggested_answers,
                "reason": analysis.decision_reason,
            }
        )

    print(json.dumps({"results": results, "tracking_summary": store.summary()}, indent=2))
    return 0


def _cmd_init_profile(args: Namespace) -> int:
    if args.destination.exists() and not args.force:
        raise ConfigError(
            f"{args.destination} already exists. Use --force to overwrite it."
        )
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.example, args.destination)
    print(f"Created editable profile template at {args.destination}")
    return 0


def _cmd_init_answers(args: Namespace) -> int:
    if args.destination.exists() and not args.force:
        raise ConfigError(
            f"{args.destination} already exists. Use --force to overwrite it."
        )
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.example, args.destination)
    print(f"Created editable application answer bank at {args.destination}")
    return 0


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="job-assistant",
        description=(
            "Prepare compliant, ATS-friendly job application materials from a stored "
            "candidate profile and job descriptions."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    links = subparsers.add_parser(
        "search-links",
        help="Generate platform search URLs for selected roles.",
    )
    links.add_argument("roles", nargs="*", help="Role names to search for.")
    links.add_argument("--all-it", action="store_true", help="Use the built-in broad IT role list.")
    links.add_argument("--location", default="", help="Optional location query.")
    links.add_argument(
        "--categories",
        nargs="*",
        choices=sorted(ROLE_CATALOG),
        help="Role categories to expand into sub-roles.",
    )
    links.add_argument(
        "--platforms",
        nargs="*",
        choices=sorted(SUPPORTED_PLATFORMS),
        help="Platforms to include. Defaults to all supported platforms.",
    )
    links.set_defaults(func=_cmd_search_links)

    plan = subparsers.add_parser(
        "search-plan",
        help="Generate an ordered portal-by-portal plan for selected roles.",
    )
    plan.add_argument("roles", nargs="*", help="Role names to search for.")
    plan.add_argument("--all-it", action="store_true", help="Use the built-in broad IT role list.")
    plan.add_argument("--location", default="", help="Optional location query.")
    plan.add_argument(
        "--categories",
        nargs="*",
        choices=sorted(ROLE_CATALOG),
        help="Role categories to expand into sub-roles.",
    )
    plan.add_argument(
        "--platforms",
        nargs="*",
        choices=sorted(SUPPORTED_PLATFORMS),
        help="Platforms to include. Defaults to all supported platforms.",
    )
    plan.add_argument(
        "--minimum-review-seconds",
        type=int,
        default=180,
        help="Minimum suggested manual review time per application.",
    )
    plan.set_defaults(func=_cmd_search_plan)

    roles = subparsers.add_parser(
        "roles",
        help="List selectable IT role categories and sub-roles.",
    )
    roles.set_defaults(func=_cmd_roles)

    answers = subparsers.add_parser(
        "answers",
        help="Manage reusable application question answers.",
    )
    answer_subparsers = answers.add_subparsers(dest="answer_command", required=True)

    answer_add = answer_subparsers.add_parser("add", help="Save an answer for reuse.")
    answer_add.add_argument("--answers", type=Path, default=DEFAULT_ANSWERS)
    answer_add.add_argument("--question", required=True)
    answer_add.add_argument("--answer", required=True)
    answer_add.add_argument("--options", nargs="*", default=[])
    answer_add.add_argument("--keywords", nargs="*", default=[])
    answer_add.add_argument("--replace", action="store_true")
    answer_add.set_defaults(func=_cmd_answers_add)

    answer_list = answer_subparsers.add_parser("list", help="List saved answers.")
    answer_list.add_argument("--answers", type=Path, default=DEFAULT_ANSWERS)
    answer_list.set_defaults(func=_cmd_answers_list)

    answer_match = answer_subparsers.add_parser("match", help="Find a saved answer for a question.")
    answer_match.add_argument("--answers", type=Path, default=DEFAULT_ANSWERS)
    answer_match.add_argument("--question", required=True)
    answer_match.add_argument("--options", nargs="*", default=[])
    answer_match.set_defaults(func=_cmd_answers_match)

    process = subparsers.add_parser(
        "process",
        help="Analyze jobs, generate tailored documents, and update tracking.",
    )
    process.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    process.add_argument("--jobs", type=Path, default=DEFAULT_JOBS)
    process.add_argument("--roles-dir", type=Path, default=DEFAULT_ROLES_DIR)
    process.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    process.add_argument("--tracking", type=Path, default=DEFAULT_TRACKING)
    process.add_argument("--answers", type=Path, default=DEFAULT_ANSWERS)
    process.add_argument("--threshold", type=int, default=85)
    process.add_argument(
        "--allow-reposts",
        action="store_true",
        help="Include URL in duplicate key so reposts or distinct listings can be prepared.",
    )
    process.set_defaults(func=_cmd_process)

    init_profile = subparsers.add_parser(
        "init-profile",
        help="Copy the example profile to data/candidate_profile.json for editing.",
    )
    init_profile.add_argument(
        "--example",
        type=Path,
        default=Path("data/candidate_profile.example.json"),
    )
    init_profile.add_argument("--destination", type=Path, default=DEFAULT_PROFILE)
    init_profile.add_argument("--force", action="store_true")
    init_profile.set_defaults(func=_cmd_init_profile)

    init_answers = subparsers.add_parser(
        "init-answers",
        help="Copy the example application answer bank for editing.",
    )
    init_answers.add_argument(
        "--example",
        type=Path,
        default=Path("data/application_answers.example.json"),
    )
    init_answers.add_argument("--destination", type=Path, default=DEFAULT_ANSWERS)
    init_answers.add_argument("--force", action="store_true")
    init_answers.set_defaults(func=_cmd_init_answers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
