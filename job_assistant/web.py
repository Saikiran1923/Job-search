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

from .database import DEFAULT_DB_PATH, JobAssistantDB
from .interview import evaluate_answer, generate_interview_questions
from .keywords import ROLE_CATALOG
from .optimizer import analyze_resume_text
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
            if method == "GET" and path == "/api/roles":
                return HTTPStatus.OK, {"roles": ROLE_CATALOG}
            if method == "GET" and path == "/api/platforms":
                return HTTPStatus.OK, {"platforms": sorted(SUPPORTED_PLATFORMS)}
            if method == "GET" and path == "/api/search/plan":
                return HTTPStatus.OK, {"steps": self._search_plan_from_query(query)}
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
