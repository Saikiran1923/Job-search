"""Local backend API and frontend server for the dashboard."""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse
import json
import mimetypes
import re
import sqlite3

from .ats_prediction import analyze_resume_workflow, apply_approved_suggestions, predict_ats_score
from .autofill import build_application_assist, build_autofill_draft
from .copilot import complete_resume_approval, extract_or_manual_job, run_manual_pipeline, validate_job_details
from .database import DEFAULT_DB_PATH, JobAssistantDB
from .interview import evaluate_answer, generate_interview_prep, generate_interview_questions
from .job_extractor import extract_job_from_url
from .keywords import ROLE_CATALOG
from .optimizer import analyze_resume_text
from .portal_sessions import detect_portal
from .resume_parser import parse_resume_upload
from .search import SUPPORTED_PLATFORMS, build_search_plan


STATIC_DIR = Path(__file__).with_name("static")


class APIError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _json_response(handler: BaseHTTPRequestHandler, status: HTTPStatus, payload: Any) -> None:
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _empty_response(handler: BaseHTTPRequestHandler, status: HTTPStatus) -> None:
    handler.send_response(status)
    handler.send_header("Content-Length", "0")
    handler.end_headers()


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    content_length = int(handler.headers.get("Content-Length", "0") or "0")
    if content_length == 0:
        return {}
    raw = handler.rfile.read(content_length)
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise APIError(HTTPStatus.BAD_REQUEST, "Request body must be valid JSON") from exc
    if not isinstance(data, dict):
        raise APIError(HTTPStatus.BAD_REQUEST, "Request body must be a JSON object")
    return data


def _required(data: dict[str, Any], *fields: str) -> None:
    missing = [field for field in fields if not str(data.get(field, "")).strip()]
    if missing:
        raise APIError(HTTPStatus.BAD_REQUEST, f"Missing required fields: {', '.join(missing)}")


def _token(handler: BaseHTTPRequestHandler) -> str:
    header = handler.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header.removeprefix("Bearer ").strip()
    return ""


def create_handler(db: JobAssistantDB) -> type[BaseHTTPRequestHandler]:
    class JobAssistantHandler(BaseHTTPRequestHandler):
        server_version = "JobAssistantAPI/0.1"

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            self._handle("GET")

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            self._handle("POST")

        def do_PUT(self) -> None:  # noqa: N802 - stdlib handler API
            self._handle("PUT")

        def do_PATCH(self) -> None:  # noqa: N802 - stdlib handler API
            self._handle("PATCH")

        def do_DELETE(self) -> None:  # noqa: N802 - stdlib handler API
            self._handle("DELETE")

        def log_message(self, format: str, *args: object) -> None:
            # Keep local dashboard output readable; audit logs capture app actions.
            return

        def _handle(self, method: str) -> None:
            try:
                parsed = urlparse(self.path)
                if not parsed.path.startswith("/api/"):
                    self._serve_static(parsed.path)
                    return
                result = self._route(method, parsed.path, parse_qs(parsed.query))
                if result is None:
                    _empty_response(self, HTTPStatus.NO_CONTENT)
                else:
                    status, payload = result
                    _json_response(self, status, payload)
            except APIError as exc:
                _json_response(self, exc.status, {"error": exc.message})
            except sqlite3.IntegrityError as exc:
                _json_response(self, HTTPStatus.CONFLICT, {"error": str(exc)})
            except ValueError as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception as exc:  # pragma: no cover - defensive boundary
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def _serve_static(self, request_path: str) -> None:
            if request_path in {"", "/"}:
                file_path = STATIC_DIR / "index.html"
            else:
                relative = request_path.lstrip("/")
                if ".." in relative:
                    raise APIError(HTTPStatus.BAD_REQUEST, "Invalid static path")
                file_path = STATIC_DIR / relative
            if not file_path.exists() or not file_path.is_file():
                file_path = STATIC_DIR / "index.html"
            body = file_path.read_bytes()
            content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _user(self) -> dict[str, Any]:
            token = _token(self)
            user = db.get_user_for_token(token) if token else None
            if not user:
                raise APIError(HTTPStatus.UNAUTHORIZED, "Authentication required")
            return user

        def _route(
            self,
            method: str,
            path: str,
            query: dict[str, list[str]],
        ) -> tuple[HTTPStatus, Any] | None:
            public_routes: dict[tuple[str, str], Callable[[], tuple[HTTPStatus, Any] | None]] = {
                ("GET", "/api/health"): lambda: (HTTPStatus.OK, {"status": "ok"}),
                ("POST", "/api/auth/register"): self._register,
                ("POST", "/api/auth/login"): self._login,
            }
            route = public_routes.get((method, path))
            if route:
                return route()

            user = self._user()
            if method == "POST" and path == "/api/auth/logout":
                db.delete_session(_token(self))
                return None
            if method == "GET" and path == "/api/me":
                return HTTPStatus.OK, {"user": user}
            if method == "GET" and path == "/api/profile":
                return HTTPStatus.OK, {"profile": db.get_profile(user["id"])}
            if method in {"POST", "PUT"} and path == "/api/profile":
                return HTTPStatus.OK, {"profile": db.save_profile(user["id"], _read_json(self))}
            if method == "DELETE" and path == "/api/profile":
                db.clear_profile(user["id"])
                return None
            if method == "GET" and path == "/api/resumes":
                return HTTPStatus.OK, {"resumes": db.list_resume_uploads(user["id"])}
            if method == "POST" and path == "/api/resumes/upload":
                data = _read_json(self)
                _required(data, "file_name")
                parsed = parse_resume_upload(
                    file_name=data["file_name"],
                    content_text=data.get("content_text", ""),
                    content_base64=data.get("content_base64", ""),
                )
                resume = db.create_resume_upload(
                    user["id"],
                    {
                        "original_file_name": data["file_name"],
                        "file_type": parsed["file_type"],
                        "resume_text": parsed["resume_text"],
                        "linked_company": data.get("linked_company", ""),
                        "linked_job": data.get("linked_job", ""),
                        "ats_before": data.get("ats_before", 0),
                        "ats_after": data.get("ats_after", 0),
                    },
                )
                return HTTPStatus.CREATED, {"resume": resume}
            if method == "GET" and path == "/api/portal-sessions":
                return HTTPStatus.OK, {"portal_sessions": db.list_portal_sessions(user["id"])}
            if method in {"POST", "PUT"} and path == "/api/portal-sessions":
                data = _read_json(self)
                _required(data, "portal", "status")
                return HTTPStatus.OK, {
                    "portal_session": db.upsert_portal_session(
                        user["id"],
                        data["portal"],
                        data["status"],
                        data.get("session_note", ""),
                    )
                }
            if method == "GET" and path == "/api/roles":
                return HTTPStatus.OK, {"roles": ROLE_CATALOG}
            if method == "GET" and path == "/api/platforms":
                return HTTPStatus.OK, {"platforms": sorted(SUPPORTED_PLATFORMS)}
            if method == "GET" and path == "/api/search/plan":
                return HTTPStatus.OK, {"steps": self._search_plan_from_query(query)}
            if method == "POST" and path == "/api/job-intake/extract":
                data = _read_json(self)
                job_url = data.get("job_url", "")
                manual_jd = data.get("manual_jd", "")
                if not job_url and not manual_jd:
                    raise APIError(HTTPStatus.BAD_REQUEST, "Provide job_url or manual_jd")
                extracted = extract_or_manual_job(
                    job_url=job_url,
                    manual_jd=manual_jd,
                    job_title=data.get("job_title", ""),
                    company_name=data.get("company_name", ""),
                )
                if extracted.get("success"):
                    valid, validation_error = validate_job_details(extracted)
                    if not valid:
                        extracted = {
                            **extracted,
                            "success": False,
                            "message": validation_error,
                            "validation_error": validation_error,
                        }
                db.save_job_intake(
                    user["id"],
                    {
                        "job_url": job_url,
                        "source": extracted.get("source", ""),
                        "extraction_status": "success" if extracted.get("success") else "manual_required",
                        "extraction_message": extracted.get("message", ""),
                        "job_details": extracted,
                    },
                )
                if extracted.get("visible_application_questions"):
                    db.save_unanswered_questions(
                        user["id"],
                        list(extracted.get("visible_application_questions", [])),
                        company_name=str(extracted.get("company_name", "")),
                        job_title=str(extracted.get("job_title", "")),
                        job_url=job_url,
                    )
                return HTTPStatus.OK, {"job_details": extracted}
            if method == "POST" and path == "/api/copilot/run":
                data = _read_json(self)
                job_details = data.get("job_details") or extract_or_manual_job(
                    job_url=data.get("job_url", ""),
                    manual_jd=data.get("manual_jd", ""),
                    job_title=data.get("job_title", ""),
                    company_name=data.get("company_name", ""),
                )
                resume_text = data.get("resume_text", "")
                if not resume_text:
                    latest_resume = db.latest_resume_upload(user["id"])
                    resume_text = latest_resume["resume_text"] if latest_resume else ""
                if not resume_text:
                    raise APIError(HTTPStatus.BAD_REQUEST, "Resume text or uploaded resume is required")
                run = run_manual_pipeline(
                    db,
                    user["id"],
                    job_details,
                    resume_text,
                    auto_run_after_intake=bool(data.get("auto_run", True)),
                )
                return HTTPStatus.OK, {"pipeline": run}
            if method == "GET" and path == "/api/applications":
                return HTTPStatus.OK, {"applications": db.list_applications(user["id"])}
            if method == "POST" and path == "/api/applications":
                data = _read_json(self)
                _required(data, "role", "company", "url")
                application = db.create_application(user["id"], data)
                return HTTPStatus.CREATED, {"application": application}
            if method == "GET" and path == "/api/analytics":
                return HTTPStatus.OK, {"analytics": db.analytics(user["id"])}
            if method == "GET" and path == "/api/recruiters":
                return HTTPStatus.OK, {"recruiters": db.list_recruiters(user["id"])}
            if method == "POST" and path == "/api/recruiters":
                data = _read_json(self)
                _required(data, "name")
                return HTTPStatus.CREATED, {"recruiter": db.create_recruiter(user["id"], data)}
            if method == "GET" and path == "/api/reminders":
                return HTTPStatus.OK, {"reminders": db.list_reminders(user["id"])}
            if method == "POST" and path == "/api/reminders":
                data = _read_json(self)
                _required(data, "title", "due_at")
                return HTTPStatus.CREATED, {"reminder": db.create_reminder(user["id"], data)}
            if method == "GET" and path == "/api/audit-logs":
                return HTTPStatus.OK, {"audit_logs": db.audit_logs(user["id"])}
            if method == "POST" and path == "/api/ats/predict":
                data = _read_json(self)
                _required(data, "resume_text")
                job_details = data.get("job_details") or data.get("job_description", "")
                prediction = predict_ats_score(data["resume_text"], job_details)
                suggestions = analyze_resume_workflow(data["resume_text"], job_details)["suggestions"]
                db.audit(user["id"], "predict", "ats", None, {"score": prediction["score"]})
                return HTTPStatus.OK, {"prediction": prediction, "suggestions": suggestions}
            if method == "POST" and path == "/api/resume/optimize":
                data = _read_json(self)
                _required(data, "resume_text")
                job_details = data.get("job_details") or data.get("job_description", "")
                approved = data.get("approved_suggestions") or []
                before = predict_ats_score(data["resume_text"], job_details)
                optimized = apply_approved_suggestions(data["resume_text"], approved)
                after = predict_ats_score(optimized["optimized_resume"], job_details)
                improvement = after["score"] - before["score"]
                version = db.create_resume_version(
                    user["id"],
                    {
                        "application_id": data.get("application_id"),
                        "original_resume": data["resume_text"],
                        "optimized_resume": optimized["optimized_resume"],
                        "job_title": (job_details or {}).get("job_title", "") if isinstance(job_details, dict) else data.get("role", ""),
                        "company": (job_details or {}).get("company_name", "") if isinstance(job_details, dict) else "",
                        "job_url": (job_details or {}).get("job_url", "") if isinstance(job_details, dict) else "",
                        "ats_before": before["score"],
                        "ats_after": after["score"],
                        "keywords_added": optimized["keywords_added"],
                    },
                )
                return HTTPStatus.OK, {
                    "before": before,
                    "after": after,
                    "improvement_percentage": improvement,
                    "optimized_resume": optimized["optimized_resume"],
                    "keywords_added": optimized["keywords_added"],
                    "resume_version": version,
                }
            if method == "POST" and path == "/api/resume/approve":
                data = _read_json(self)
                _required(data, "resume_text")
                result = complete_resume_approval(
                    db,
                    user["id"],
                    data["resume_text"],
                    data.get("job_details") or {},
                    data.get("approved_suggestions") or [],
                    data.get("application_id"),
                )
                return HTTPStatus.OK, result
            if method == "GET" and path == "/api/resume/versions":
                return HTTPStatus.OK, {"resume_versions": db.list_resume_versions(user["id"])}
            if method == "GET" and path == "/api/questions":
                status = query.get("status", [None])[0]
                return HTTPStatus.OK, {"questions": db.list_questions(user["id"], status=status)}
            if method == "POST" and path == "/api/questions/unanswered":
                data = _read_json(self)
                questions = data.get("questions") or []
                saved = db.save_unanswered_questions(
                    user["id"],
                    questions,
                    company_name=data.get("company_name", ""),
                    job_title=data.get("job_title", ""),
                    job_url=data.get("job_url", ""),
                )
                return HTTPStatus.CREATED, {"questions": saved}
            if method == "POST" and path == "/api/questions/bulk-delete":
                data = _read_json(self)
                deleted = db.bulk_delete_questions(user["id"], [int(item) for item in data.get("question_ids", [])])
                return HTTPStatus.OK, {"deleted": deleted}
            if method == "POST" and path == "/api/questions/clear-unanswered":
                deleted = db.clear_unanswered_questions(user["id"])
                return HTTPStatus.OK, {"deleted": deleted}
            if method == "POST" and path in {"/api/autofill/draft", "/api/application-assist/draft"}:
                data = _read_json(self)
                questions = data.get("questions") or []
                answer_lookup = {}
                for question in questions:
                    match = db.find_answer_for_question(user["id"], str(question.get("question", "")))
                    if match:
                        answer_lookup[str(question.get("question", ""))] = match["answer"]
                unanswered = [
                    question for question in questions if str(question.get("question", "")) not in answer_lookup
                ]
                if unanswered:
                    db.save_unanswered_questions(
                        user["id"],
                        unanswered,
                        company_name=data.get("company_name", ""),
                        job_title=data.get("job_title", ""),
                        job_url=data.get("job_url", ""),
                    )
                profile = db.get_profile(user["id"])
                return HTTPStatus.OK, {
                    "application_assist": build_application_assist(profile, questions, answer_lookup),
                    "autofill": build_autofill_draft(questions, answer_lookup),
                }
            if method == "POST" and path == "/api/ats/analyze":
                data = _read_json(self)
                _required(data, "resume_text", "job_description")
                result = analyze_resume_text(
                    resume_text=data["resume_text"],
                    job_description=data["job_description"],
                    role=data.get("role", "General IT"),
                    roles_dir=Path(data.get("roles_dir", "data/roles")),
                )
                db.audit(user["id"], "analyze", "ats", None, {"role": result["role"]})
                return HTTPStatus.OK, {"analysis": result}
            if method == "POST" and path == "/api/interview/questions":
                data = _read_json(self)
                _required(data, "job_description")
                questions = generate_interview_questions(
                    job_description=data["job_description"],
                    role=data.get("role", "IT Role"),
                    count=int(data.get("count", 8)),
                )
                db.audit(user["id"], "generate", "interview_questions", None, {"role": data.get("role", "")})
                return HTTPStatus.OK, {"questions": questions}
            if method == "POST" and path == "/api/interview/prep":
                data = _read_json(self)
                _required(data, "optimized_resume", "job_description")
                questions = generate_interview_prep(
                    optimized_resume=data["optimized_resume"],
                    job_description=data["job_description"],
                    role=data.get("role", "IT Role"),
                )
                flat_questions = [*questions["level_1"], *questions["level_2"]]
                if data.get("save"):
                    db.save_interview_questions(user["id"], flat_questions, data.get("application_id"))
                db.audit(user["id"], "generate", "interview_prep", None, {"count": len(flat_questions)})
                return HTTPStatus.OK, {"questions": questions}
            if method == "GET" and path == "/api/interview/saved":
                return HTTPStatus.OK, {"questions": db.list_interview_questions(user["id"])}
            if method == "POST" and path == "/api/interview/evaluate":
                data = _read_json(self)
                _required(data, "question", "answer")
                evaluation = evaluate_answer(
                    question=data["question"],
                    answer=data["answer"],
                    job_description=data.get("job_description", ""),
                )
                db.audit(user["id"], "evaluate", "interview_answer", None, {"score": evaluation["score"]})
                return HTTPStatus.OK, {"evaluation": evaluation}

            application_match = re.fullmatch(r"/api/applications/(\d+)", path)
            if application_match:
                application_id = int(application_match.group(1))
                if method == "GET":
                    application = db.get_application(user["id"], application_id)
                    if not application:
                        raise APIError(HTTPStatus.NOT_FOUND, "Application not found")
                    return HTTPStatus.OK, {"application": application}
                if method in {"PUT", "PATCH"}:
                    application = db.update_application(user["id"], application_id, _read_json(self))
                    if not application:
                        raise APIError(HTTPStatus.NOT_FOUND, "Application not found")
                    return HTTPStatus.OK, {"application": application}
                if method == "DELETE":
                    if not db.delete_application(user["id"], application_id):
                        raise APIError(HTTPStatus.NOT_FOUND, "Application not found")
                    return None

            question_match = re.fullmatch(r"/api/questions/(\d+)/answer", path)
            if question_match and method in {"POST", "PUT", "PATCH"}:
                data = _read_json(self)
                _required(data, "answer")
                question = db.answer_question(user["id"], int(question_match.group(1)), data["answer"])
                if not question:
                    raise APIError(HTTPStatus.NOT_FOUND, "Question not found")
                return HTTPStatus.OK, {"question": question}

            question_delete_match = re.fullmatch(r"/api/questions/(\d+)", path)
            if question_delete_match and method == "DELETE":
                if not db.delete_question(user["id"], int(question_delete_match.group(1))):
                    raise APIError(HTTPStatus.NOT_FOUND, "Question not found")
                return HTTPStatus.OK, {"message": "Question deleted"}

            interview_match = re.fullmatch(r"/api/interview/questions/(\d+)", path)
            if interview_match and method in {"PATCH", "PUT"}:
                question = db.update_interview_question(user["id"], int(interview_match.group(1)), _read_json(self))
                if not question:
                    raise APIError(HTTPStatus.NOT_FOUND, "Interview question not found")
                return HTTPStatus.OK, {"question": question}

            raise APIError(HTTPStatus.NOT_FOUND, "Route not found")

        def _register(self) -> tuple[HTTPStatus, Any]:
            data = _read_json(self)
            _required(data, "name", "email", "password")
            if len(data["password"]) < 8:
                raise APIError(HTTPStatus.BAD_REQUEST, "Password must be at least 8 characters")
            user = db.create_user(data["name"], data["email"], data["password"])
            token = db.create_session(user["id"])
            return HTTPStatus.CREATED, {"token": token, "user": user}

        def _login(self) -> tuple[HTTPStatus, Any]:
            data = _read_json(self)
            _required(data, "email", "password")
            user = db.authenticate(data["email"], data["password"])
            if not user:
                raise APIError(HTTPStatus.UNAUTHORIZED, "Invalid email or password")
            token = db.create_session(user["id"])
            return HTTPStatus.OK, {"token": token, "user": user}

        def _search_plan_from_query(self, query: dict[str, list[str]]) -> list[dict[str, object]]:
            roles = query.get("roles", [])
            categories = query.get("categories", [])
            platforms = query.get("platforms", [])
            all_it = query.get("all_it", ["false"])[0].lower() in {"1", "true", "yes"}
            location = query.get("location", [""])[0]
            return build_search_plan(
                roles=roles,
                platforms=platforms or None,
                location=location,
                all_it=all_it,
                categories=categories or None,
            )

    return JobAssistantHandler


def run_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    db = JobAssistantDB(db_path)
    server = ThreadingHTTPServer((host, port), create_handler(db))
    print(f"Job Assistant dashboard running at http://{host}:{port}")
    print(f"SQLite database: {db_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard server.")
    finally:
        server.server_close()
