"""SQLite persistence layer for the web dashboard API."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
import base64
import hashlib
import hmac
import json
import secrets
import sqlite3


DEFAULT_DB_PATH = Path("applications/job_assistant.sqlite3")
STATUSES = ("saved", "applied", "interviewing", "offer", "rejected")
SUPPORTED_PORTALS = (
    "LinkedIn",
    "Indeed",
    "Dice",
    "Monster",
    "ZipRecruiter",
    "Workday",
    "Greenhouse",
    "Lever",
    "iCIMS",
    "Taleo",
    "SuccessFactors",
    "Company career sites",
    "Unknown job sites",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _normalize_question(value: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 200_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "$".join(
        [
            "pbkdf2_sha256",
            str(iterations),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_text.encode("ascii"))
        expected = base64.b64decode(digest_text.encode("ascii"))
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


class JobAssistantDB:
    """Small repository wrapper around SQLite."""

    def __init__(self, path: Path = DEFAULT_DB_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def init(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS recruiters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    email TEXT DEFAULT '',
                    phone TEXT DEFAULT '',
                    company TEXT DEFAULT '',
                    linkedin TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    recruiter_id INTEGER REFERENCES recruiters(id) ON DELETE SET NULL,
                    role TEXT NOT NULL,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    url TEXT NOT NULL,
                    source TEXT DEFAULT '',
                    location TEXT DEFAULT '',
                    salary TEXT DEFAULT '',
                    work_mode TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'saved',
                    ats_score INTEGER DEFAULT 0,
                    original_ats_score INTEGER DEFAULT 0,
                    optimized_ats_score INTEGER DEFAULT 0,
                    matched_skills TEXT DEFAULT '[]',
                    missing_skills TEXT DEFAULT '[]',
                    resume_path TEXT DEFAULT '',
                    cover_letter_path TEXT DEFAULT '',
                    resume_version TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    follow_up_at TEXT DEFAULT '',
                    applied_at TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, company, role, url)
                );

                CREATE TABLE IF NOT EXISTS status_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    from_status TEXT DEFAULT '',
                    to_status TEXT NOT NULL,
                    note TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    application_id INTEGER REFERENCES applications(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    notes TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS resume_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    application_id INTEGER REFERENCES applications(id) ON DELETE SET NULL,
                    label TEXT NOT NULL,
                    path TEXT DEFAULT '',
                    ats_score INTEGER DEFAULT 0,
                    notes TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS job_intakes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    job_url TEXT NOT NULL,
                    source TEXT DEFAULT '',
                    extraction_status TEXT NOT NULL,
                    extraction_message TEXT DEFAULT '',
                    job_details TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS question_bank (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    question TEXT NOT NULL,
                    normalized_question TEXT NOT NULL,
                    answer TEXT DEFAULT '',
                    options TEXT DEFAULT '[]',
                    company_name TEXT DEFAULT '',
                    job_title TEXT DEFAULT '',
                    job_url TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'unanswered',
                    usage_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS interview_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    application_id INTEGER REFERENCES applications(id) ON DELETE SET NULL,
                    question TEXT NOT NULL,
                    difficulty_level TEXT NOT NULL,
                    source TEXT NOT NULL,
                    suggested_answer TEXT DEFAULT '',
                    keywords TEXT DEFAULT '[]',
                    confidence_score INTEGER DEFAULT 0,
                    saved INTEGER NOT NULL DEFAULT 0,
                    practiced INTEGER NOT NULL DEFAULT 0,
                    user_answer TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS profiles (
                    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    first_name TEXT DEFAULT '',
                    last_name TEXT DEFAULT '',
                    email TEXT DEFAULT '',
                    phone TEXT DEFAULT '',
                    address TEXT DEFAULT '',
                    city TEXT DEFAULT '',
                    state TEXT DEFAULT '',
                    zip TEXT DEFAULT '',
                    country TEXT DEFAULT '',
                    linkedin_url TEXT DEFAULT '',
                    portfolio_url TEXT DEFAULT '',
                    github_url TEXT DEFAULT '',
                    education TEXT DEFAULT '',
                    certifications TEXT DEFAULT '',
                    skills TEXT DEFAULT '',
                    total_experience TEXT DEFAULT '',
                    current_job_title TEXT DEFAULT '',
                    work_authorization TEXT DEFAULT '',
                    sponsorship_required TEXT DEFAULT '',
                    relocation_preference TEXT DEFAULT '',
                    work_mode_preference TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS resume_uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    original_file_name TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    resume_text TEXT NOT NULL,
                    upload_date TEXT NOT NULL,
                    version_number INTEGER NOT NULL,
                    linked_company TEXT DEFAULT '',
                    linked_job TEXT DEFAULT '',
                    ats_before INTEGER DEFAULT 0,
                    ats_after INTEGER DEFAULT 0,
                    is_master INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS portal_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    portal TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Not connected',
                    session_note TEXT DEFAULT '',
                    last_checked_at TEXT DEFAULT '',
                    expires_at TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, portal)
                );

                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    job_url TEXT DEFAULT '',
                    job_details TEXT DEFAULT '{}',
                    resume_text TEXT DEFAULT '',
                    statuses TEXT DEFAULT '{}',
                    ats_before INTEGER DEFAULT 0,
                    ats_after INTEGER DEFAULT 0,
                    optimized_resume TEXT DEFAULT '',
                    suggestions TEXT DEFAULT '[]',
                    application_assist TEXT DEFAULT '{}',
                    application_id INTEGER REFERENCES applications(id) ON DELETE SET NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    action TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id INTEGER,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                """
            )
            self._migrate(connection)

    def _migrate(self, connection: sqlite3.Connection) -> None:
        application_columns = {
            "ats_improvement": "INTEGER DEFAULT 0",
            "unanswered_questions_count": "INTEGER DEFAULT 0",
            "interview_questions_generated": "INTEGER DEFAULT 0",
            "employment_type": "TEXT DEFAULT ''",
            "salary_range": "TEXT DEFAULT ''",
        }
        existing_app_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(applications)").fetchall()
        }
        for column, definition in application_columns.items():
            if column not in existing_app_columns:
                connection.execute(f"ALTER TABLE applications ADD COLUMN {column} {definition}")

        question_columns = {
            "deleted": "INTEGER NOT NULL DEFAULT 0",
            "deleted_at": "TEXT DEFAULT ''",
        }
        existing_question_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(question_bank)").fetchall()
        }
        for column, definition in question_columns.items():
            if column not in existing_question_columns:
                connection.execute(f"ALTER TABLE question_bank ADD COLUMN {column} {definition}")

        resume_columns = {
            "original_resume": "TEXT DEFAULT ''",
            "optimized_resume": "TEXT DEFAULT ''",
            "version_number": "INTEGER DEFAULT 1",
            "job_title": "TEXT DEFAULT ''",
            "company": "TEXT DEFAULT ''",
            "job_url": "TEXT DEFAULT ''",
            "ats_before": "INTEGER DEFAULT 0",
            "ats_after": "INTEGER DEFAULT 0",
            "keywords_added": "TEXT DEFAULT '[]'",
        }
        existing = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(resume_versions)").fetchall()
        }
        for column, definition in resume_columns.items():
            if column not in existing:
                connection.execute(f"ALTER TABLE resume_versions ADD COLUMN {column} {definition}")

        recruiter_columns = {
            "direct_phone": "TEXT DEFAULT ''",
            "mobile_number": "TEXT DEFAULT ''",
            "office_number": "TEXT DEFAULT ''",
            "last_contact_date": "TEXT DEFAULT ''",
            "follow_up_date": "TEXT DEFAULT ''",
        }
        existing_recruiter_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(recruiters)").fetchall()
        }
        for column, definition in recruiter_columns.items():
            if column not in existing_recruiter_columns:
                connection.execute(f"ALTER TABLE recruiters ADD COLUMN {column} {definition}")

    def create_user(self, name: str, email: str, password: str, role: str = "user") -> dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (name, email, password_hash, role, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name.strip(), email.lower().strip(), hash_password(password), role, timestamp),
            )
            user = self.get_user(cursor.lastrowid, connection=connection)
            self.audit(cursor.lastrowid, "register", "user", cursor.lastrowid, {}, connection)
            return user

    def get_user(
        self,
        user_id: int,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        def _get(conn: sqlite3.Connection) -> dict[str, Any]:
            row = conn.execute(
                "SELECT id, name, email, role, created_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                raise KeyError("User not found")
            return dict(row)

        if connection:
            return _get(connection)
        with self.connect() as conn:
            return _get(conn)

    def authenticate(self, email: str, password: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE email = ?",
                (email.lower().strip(),),
            ).fetchone()
            if not row or not verify_password(password, row["password_hash"]):
                return None
            user = {
                "id": row["id"],
                "name": row["name"],
                "email": row["email"],
                "role": row["role"],
                "created_at": row["created_at"],
            }
            self.audit(user["id"], "login", "user", user["id"], {}, connection)
            return user

    def create_session(self, user_id: int, hours: int = 24) -> str:
        token = secrets.token_urlsafe(32)
        timestamp = now_iso()
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
                (token, user_id, expires_at, timestamp),
            )
        return token

    def get_user_for_token(self, token: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT users.id, users.name, users.email, users.role, users.created_at
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token = ? AND sessions.expires_at > ?
                """,
                (token, now_iso()),
            ).fetchone()
            return dict(row) if row else None

    def delete_session(self, token: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def save_profile(self, user_id: int, data: dict[str, Any]) -> dict[str, Any]:
        timestamp = now_iso()
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "address",
            "city",
            "state",
            "zip",
            "country",
            "linkedin_url",
            "portfolio_url",
            "github_url",
            "education",
            "certifications",
            "skills",
            "total_experience",
            "current_job_title",
            "work_authorization",
            "sponsorship_required",
            "relocation_preference",
            "work_mode_preference",
        ]
        values = {field: str(data.get(field, "")).strip() for field in fields}
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT user_id FROM profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if existing:
                assignments = ", ".join(f"{field} = ?" for field in fields)
                connection.execute(
                    f"UPDATE profiles SET {assignments}, updated_at = ? WHERE user_id = ?",
                    [values[field] for field in fields] + [timestamp, user_id],
                )
                action = "update"
            else:
                connection.execute(
                    f"""
                    INSERT INTO profiles (
                        user_id, {', '.join(fields)}, created_at, updated_at
                    )
                    VALUES ({', '.join(['?'] * (len(fields) + 3))})
                    """,
                    [user_id] + [values[field] for field in fields] + [timestamp, timestamp],
                )
                action = "create"
            self.audit(user_id, action, "profile", user_id, values, connection)
            return self.get_profile(user_id, connection=connection)

    def get_profile(
        self,
        user_id: int,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        def _get(conn: sqlite3.Connection) -> dict[str, Any]:
            row = conn.execute("SELECT * FROM profiles WHERE user_id = ?", (user_id,)).fetchone()
            return dict(row) if row else {}

        if connection:
            return _get(connection)
        with self.connect() as conn:
            return _get(conn)

    def clear_profile(self, user_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM profiles WHERE user_id = ?", (user_id,))
            deleted = cursor.rowcount > 0
            if deleted:
                self.audit(user_id, "delete", "profile", user_id, {}, connection)
            return deleted

    def profile_fields_ready_count(self, user_id: int) -> int:
        profile = self.get_profile(user_id)
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "address",
            "city",
            "state",
            "zip",
            "country",
            "linkedin_url",
            "portfolio_url",
            "education",
            "skills",
            "work_authorization",
            "sponsorship_required",
        ]
        return sum(1 for field in fields if str(profile.get(field, "")).strip())

    def create_resume_upload(self, user_id: int, data: dict[str, Any]) -> dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(version_number), 0) AS max_version FROM resume_uploads WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            version_number = int(data.get("version_number") or (row["max_version"] + 1))
            cursor = connection.execute(
                """
                INSERT INTO resume_uploads (
                    user_id, original_file_name, file_type, resume_text, upload_date, version_number,
                    linked_company, linked_job, ats_before, ats_after, is_master
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    data.get("original_file_name", ""),
                    data.get("file_type", ""),
                    data.get("resume_text", ""),
                    timestamp,
                    version_number,
                    data.get("linked_company", ""),
                    data.get("linked_job", ""),
                    int(data.get("ats_before") or 0),
                    int(data.get("ats_after") or 0),
                    1 if data.get("is_master", True) else 0,
                ),
            )
            self.audit(user_id, "create", "resume_upload", cursor.lastrowid, data, connection)
            row = connection.execute(
                "SELECT * FROM resume_uploads WHERE id = ? AND user_id = ?",
                (cursor.lastrowid, user_id),
            ).fetchone()
            return dict(row)

    def list_resume_uploads(self, user_id: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM resume_uploads WHERE user_id = ? ORDER BY version_number DESC",
                    (user_id,),
                ).fetchall()
            ]

    def latest_resume_upload(self, user_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM resume_uploads WHERE user_id = ? ORDER BY version_number DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            return dict(row) if row else None

    def upsert_portal_session(self, user_id: int, portal: str, status: str, note: str = "") -> dict[str, Any]:
        if portal not in SUPPORTED_PORTALS:
            portal = "Unknown job sites"
        if status not in {"Logged in", "Not connected", "Session expired"}:
            raise ValueError("Unsupported portal session status")
        timestamp = now_iso()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO portal_sessions (
                    user_id, portal, status, session_note, last_checked_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, portal) DO UPDATE SET
                    status = excluded.status,
                    session_note = excluded.session_note,
                    last_checked_at = excluded.last_checked_at,
                    updated_at = excluded.updated_at
                """,
                (user_id, portal, status, note, timestamp, timestamp, timestamp),
            )
            self.audit(user_id, "update", "portal_session", None, {"portal": portal, "status": status}, connection)
            row = connection.execute(
                "SELECT * FROM portal_sessions WHERE user_id = ? AND portal = ?",
                (user_id, portal),
            ).fetchone()
            return dict(row)

    def list_portal_sessions(self, user_id: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            existing = {
                row["portal"]: dict(row)
                for row in connection.execute(
                    "SELECT * FROM portal_sessions WHERE user_id = ?",
                    (user_id,),
                ).fetchall()
            }
        sessions = []
        for portal in SUPPORTED_PORTALS:
            sessions.append(
                existing.get(
                    portal,
                    {
                        "portal": portal,
                        "status": "Not connected",
                        "session_note": "",
                        "last_checked_at": "",
                        "expires_at": "",
                    },
                )
            )
        return sessions

    def audit(
        self,
        user_id: int | None,
        action: str,
        entity_type: str,
        entity_id: int | None,
        metadata: dict[str, Any] | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        values = (user_id, action, entity_type, entity_id, _json_dumps(metadata or {}), now_iso())
        if connection:
            connection.execute(
                """
                INSERT INTO audit_logs (user_id, action, entity_type, entity_id, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            return
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs (user_id, action, entity_type, entity_id, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                values,
            )

    def list_applications(self, user_id: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT applications.*, recruiters.name AS recruiter_name, recruiters.email AS recruiter_email
                FROM applications
                LEFT JOIN recruiters ON recruiters.id = applications.recruiter_id
                WHERE applications.user_id = ?
                ORDER BY applications.updated_at DESC
                """,
                (user_id,),
            ).fetchall()
            return [self._application_from_row(row) for row in rows]

    def get_application(self, user_id: int, application_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT applications.*, recruiters.name AS recruiter_name, recruiters.email AS recruiter_email
                FROM applications
                LEFT JOIN recruiters ON recruiters.id = applications.recruiter_id
                WHERE applications.user_id = ? AND applications.id = ?
                """,
                (user_id, application_id),
            ).fetchone()
            return self._application_from_row(row) if row else None

    def create_application(self, user_id: int, data: dict[str, Any]) -> dict[str, Any]:
        timestamp = now_iso()
        status = data.get("status") or "saved"
        if status not in STATUSES:
            raise ValueError(f"Unsupported status: {status}")
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO applications (
                    user_id, recruiter_id, role, title, company, url, source, location, salary,
                    work_mode, status, ats_score, original_ats_score, optimized_ats_score,
                    matched_skills, missing_skills, resume_path, cover_letter_path, resume_version,
                    notes, follow_up_at, applied_at, ats_improvement, unanswered_questions_count,
                    interview_questions_generated, employment_type, salary_range, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    data.get("recruiter_id"),
                    data.get("role", "").strip(),
                    data.get("title", data.get("role", "")).strip(),
                    data.get("company", "").strip(),
                    data.get("url", "").strip(),
                    data.get("source", "").strip(),
                    data.get("location", "").strip(),
                    data.get("salary", "").strip(),
                    data.get("work_mode", "").strip(),
                    status,
                    int(data.get("ats_score") or 0),
                    int(data.get("original_ats_score") or 0),
                    int(data.get("optimized_ats_score") or 0),
                    _json_dumps(data.get("matched_skills") or []),
                    _json_dumps(data.get("missing_skills") or []),
                    data.get("resume_path", "").strip(),
                    data.get("cover_letter_path", "").strip(),
                    data.get("resume_version", "").strip(),
                    data.get("notes", "").strip(),
                    data.get("follow_up_at", "").strip(),
                    data.get("applied_at", "").strip(),
                    int(data.get("ats_improvement") or 0),
                    int(data.get("unanswered_questions_count") or 0),
                    int(data.get("interview_questions_generated") or 0),
                    data.get("employment_type", "").strip(),
                    data.get("salary_range", "").strip(),
                    timestamp,
                    timestamp,
                ),
            )
            application_id = cursor.lastrowid
            connection.execute(
                """
                INSERT INTO status_history (application_id, user_id, from_status, to_status, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (application_id, user_id, "", status, "Application created", timestamp),
            )
            self.audit(user_id, "create", "application", application_id, data, connection)
            row = connection.execute(
                """
                SELECT applications.*, recruiters.name AS recruiter_name, recruiters.email AS recruiter_email
                FROM applications
                LEFT JOIN recruiters ON recruiters.id = applications.recruiter_id
                WHERE applications.user_id = ? AND applications.id = ?
                """,
                (user_id, application_id),
            ).fetchone()
            return self._application_from_row(row)

    def update_application(
        self,
        user_id: int,
        application_id: int,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        current = self.get_application(user_id, application_id)
        if not current:
            return None
        allowed = {
            "recruiter_id",
            "role",
            "title",
            "company",
            "url",
            "source",
            "location",
            "salary",
            "work_mode",
            "status",
            "ats_score",
            "original_ats_score",
            "optimized_ats_score",
            "matched_skills",
            "missing_skills",
            "resume_path",
            "cover_letter_path",
            "resume_version",
            "notes",
            "follow_up_at",
            "applied_at",
            "ats_improvement",
            "unanswered_questions_count",
            "interview_questions_generated",
            "employment_type",
            "salary_range",
        }
        updates = {key: value for key, value in data.items() if key in allowed}
        if "status" in updates and updates["status"] not in STATUSES:
            raise ValueError(f"Unsupported status: {updates['status']}")
        if not updates:
            return current

        columns = []
        values: list[Any] = []
        for key, value in updates.items():
            columns.append(f"{key} = ?")
            if key in {"matched_skills", "missing_skills"}:
                values.append(_json_dumps(value or []))
            elif key in {"ats_score", "original_ats_score", "optimized_ats_score", "ats_improvement", "unanswered_questions_count", "interview_questions_generated"}:
                values.append(int(value or 0))
            else:
                values.append(value)
        columns.append("updated_at = ?")
        values.append(now_iso())
        values.extend([user_id, application_id])

        with self.connect() as connection:
            connection.execute(
                f"UPDATE applications SET {', '.join(columns)} WHERE user_id = ? AND id = ?",
                values,
            )
            if "status" in updates and updates["status"] != current["status"]:
                connection.execute(
                    """
                    INSERT INTO status_history (application_id, user_id, from_status, to_status, note, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        application_id,
                        user_id,
                        current["status"],
                        updates["status"],
                        data.get("status_note", ""),
                        now_iso(),
                    ),
                )
            self.audit(user_id, "update", "application", application_id, updates, connection)
        return self.get_application(user_id, application_id)

    def delete_application(self, user_id: int, application_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM applications WHERE user_id = ? AND id = ?",
                (user_id, application_id),
            )
            deleted = cursor.rowcount > 0
            if deleted:
                self.audit(user_id, "delete", "application", application_id, {}, connection)
            return deleted

    def list_recruiters(self, user_id: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM recruiters WHERE user_id = ? ORDER BY updated_at DESC",
                    (user_id,),
                ).fetchall()
            ]

    def create_recruiter(self, user_id: int, data: dict[str, Any]) -> dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO recruiters (
                    user_id, name, email, phone, company, linkedin, notes,
                    direct_phone, mobile_number, office_number, last_contact_date,
                    follow_up_date, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    data.get("name", "").strip(),
                    data.get("email", "").strip(),
                    data.get("phone", "").strip(),
                    data.get("company", "").strip(),
                    data.get("linkedin", "").strip(),
                    data.get("notes", "").strip(),
                    data.get("direct_phone", "").strip(),
                    data.get("mobile_number", "").strip(),
                    data.get("office_number", "").strip(),
                    data.get("last_contact_date", "").strip(),
                    data.get("follow_up_date", "").strip(),
                    timestamp,
                    timestamp,
                ),
            )
            recruiter = dict(
                connection.execute(
                    "SELECT * FROM recruiters WHERE id = ? AND user_id = ?",
                    (cursor.lastrowid, user_id),
                ).fetchone()
            )
            self.audit(user_id, "create", "recruiter", cursor.lastrowid, data, connection)
            return recruiter

    def list_reminders(self, user_id: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT reminders.*, applications.company, applications.role
                    FROM reminders
                    LEFT JOIN applications ON applications.id = reminders.application_id
                    WHERE reminders.user_id = ?
                    ORDER BY reminders.due_at ASC
                    """,
                    (user_id,),
                ).fetchall()
            ]

    def create_reminder(self, user_id: int, data: dict[str, Any]) -> dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO reminders (user_id, application_id, title, due_at, status, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    data.get("application_id"),
                    data.get("title", "").strip(),
                    data.get("due_at", "").strip(),
                    data.get("status", "open").strip(),
                    data.get("notes", "").strip(),
                    timestamp,
                    timestamp,
                ),
            )
            reminder = dict(
                connection.execute(
                    "SELECT * FROM reminders WHERE id = ? AND user_id = ?",
                    (cursor.lastrowid, user_id),
                ).fetchone()
            )
            self.audit(user_id, "create", "reminder", cursor.lastrowid, data, connection)
            return reminder

    def save_job_intake(self, user_id: int, data: dict[str, Any]) -> dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO job_intakes (
                    user_id, job_url, source, extraction_status, extraction_message, job_details, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    data.get("job_url", ""),
                    data.get("source", ""),
                    data.get("extraction_status", ""),
                    data.get("extraction_message", ""),
                    _json_dumps(data.get("job_details") or {}),
                    timestamp,
                ),
            )
            self.audit(user_id, "create", "job_intake", cursor.lastrowid, data, connection)
            row = connection.execute(
                "SELECT * FROM job_intakes WHERE id = ? AND user_id = ?",
                (cursor.lastrowid, user_id),
            ).fetchone()
            item = dict(row)
            item["job_details"] = _json_loads(item.get("job_details"), {})
            return item

    def create_resume_version(self, user_id: int, data: dict[str, Any]) -> dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(version_number), 0) AS max_version FROM resume_versions WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            version_number = int(data.get("version_number") or (row["max_version"] + 1))
            label = data.get("label") or f"Resume v{version_number}"
            cursor = connection.execute(
                """
                INSERT INTO resume_versions (
                    user_id, application_id, label, path, ats_score, notes, original_resume,
                    optimized_resume, version_number, job_title, company, job_url, ats_before,
                    ats_after, keywords_added, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    data.get("application_id"),
                    label,
                    data.get("path", ""),
                    int(data.get("ats_after") or data.get("ats_score") or 0),
                    data.get("notes", ""),
                    data.get("original_resume", ""),
                    data.get("optimized_resume", ""),
                    version_number,
                    data.get("job_title", ""),
                    data.get("company", ""),
                    data.get("job_url", ""),
                    int(data.get("ats_before") or 0),
                    int(data.get("ats_after") or 0),
                    _json_dumps(data.get("keywords_added") or []),
                    timestamp,
                ),
            )
            self.audit(user_id, "create", "resume_version", cursor.lastrowid, data, connection)
            return self._resume_version_by_id(connection, user_id, cursor.lastrowid)

    def list_resume_versions(self, user_id: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM resume_versions WHERE user_id = ? ORDER BY version_number DESC, created_at DESC",
                (user_id,),
            ).fetchall()
            return [self._resume_version_from_row(row) for row in rows]

    def save_unanswered_questions(
        self,
        user_id: int,
        questions: list[dict[str, Any]],
        company_name: str = "",
        job_title: str = "",
        job_url: str = "",
    ) -> list[dict[str, Any]]:
        saved = []
        timestamp = now_iso()
        with self.connect() as connection:
            for question_data in questions:
                question = str(question_data.get("question", "")).strip()
                if not question:
                    continue
                normalized = _normalize_question(question)
                existing = connection.execute(
                    "SELECT * FROM question_bank WHERE user_id = ? AND normalized_question = ? AND deleted = 0",
                    (user_id, normalized),
                ).fetchone()
                if existing:
                    saved.append(self._question_from_row(existing))
                    continue
                cursor = connection.execute(
                    """
                    INSERT INTO question_bank (
                        user_id, question, normalized_question, answer, options, company_name,
                        job_title, job_url, status, usage_count, created_at, updated_at
                    )
                    VALUES (?, ?, ?, '', ?, ?, ?, ?, 'unanswered', 0, ?, ?)
                    """,
                    (
                        user_id,
                        question,
                        normalized,
                        _json_dumps(question_data.get("options") or []),
                        company_name,
                        job_title,
                        job_url,
                        timestamp,
                        timestamp,
                    ),
                )
                self.audit(user_id, "create", "question", cursor.lastrowid, {"question": question}, connection)
                saved.append(
                    self._question_from_row(
                        connection.execute(
                            "SELECT * FROM question_bank WHERE id = ? AND user_id = ?",
                            (cursor.lastrowid, user_id),
                        ).fetchone()
                    )
                )
        return saved

    def answer_question(self, user_id: int, question_id: int, answer: str) -> dict[str, Any] | None:
        timestamp = now_iso()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE question_bank
                SET answer = ?, status = 'answered', updated_at = ?
                WHERE user_id = ? AND id = ? AND deleted = 0
                """,
                (answer.strip(), timestamp, user_id, question_id),
            )
            if cursor.rowcount == 0:
                return None
            self.audit(user_id, "answer", "question", question_id, {}, connection)
            row = connection.execute(
                "SELECT * FROM question_bank WHERE id = ? AND user_id = ?",
                (question_id, user_id),
            ).fetchone()
            return self._question_from_row(row)

    def list_questions(self, user_id: int, status: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as connection:
            if status:
                rows = connection.execute(
                    "SELECT * FROM question_bank WHERE user_id = ? AND status = ? AND deleted = 0 ORDER BY updated_at DESC",
                    (user_id, status),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM question_bank WHERE user_id = ? AND deleted = 0 ORDER BY updated_at DESC",
                    (user_id,),
                ).fetchall()
            return [self._question_from_row(row) for row in rows]

    def find_answer_for_question(self, user_id: int, question: str) -> dict[str, Any] | None:
        normalized = _normalize_question(question)
        tokens = set(normalized.split())
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM question_bank WHERE user_id = ? AND status = 'answered' AND deleted = 0",
                (user_id,),
            ).fetchall()
            best: tuple[float, sqlite3.Row] | None = None
            for row in rows:
                row_tokens = set(str(row["normalized_question"]).split())
                if not row_tokens:
                    continue
                score = len(tokens & row_tokens) / len(tokens | row_tokens)
                if best is None or score > best[0]:
                    best = (score, row)
            if not best or best[0] < 0.35:
                return None
            connection.execute(
                "UPDATE question_bank SET usage_count = usage_count + 1, updated_at = ? WHERE id = ?",
                (now_iso(), best[1]["id"]),
            )
            return self._question_from_row(best[1])

    def delete_question(self, user_id: int, question_id: int) -> bool:
        timestamp = now_iso()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE question_bank
                SET deleted = 1, deleted_at = ?, updated_at = ?
                WHERE user_id = ? AND id = ?
                """,
                (timestamp, timestamp, user_id, question_id),
            )
            deleted = cursor.rowcount > 0
            if deleted:
                self.audit(user_id, "delete", "question", question_id, {}, connection)
            return deleted

    def bulk_delete_questions(self, user_id: int, question_ids: list[int]) -> int:
        if not question_ids:
            return 0
        timestamp = now_iso()
        placeholders = ", ".join("?" for _ in question_ids)
        with self.connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE question_bank
                SET deleted = 1, deleted_at = ?, updated_at = ?
                WHERE user_id = ? AND id IN ({placeholders})
                """,
                [timestamp, timestamp, user_id, *question_ids],
            )
            self.audit(user_id, "bulk_delete", "question", None, {"count": cursor.rowcount}, connection)
            return cursor.rowcount

    def clear_unanswered_questions(self, user_id: int) -> int:
        timestamp = now_iso()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE question_bank
                SET deleted = 1, deleted_at = ?, updated_at = ?
                WHERE user_id = ? AND status = 'unanswered' AND deleted = 0
                """,
                (timestamp, timestamp, user_id),
            )
            self.audit(user_id, "clear_unanswered", "question", None, {"count": cursor.rowcount}, connection)
            return cursor.rowcount

    def save_interview_questions(
        self,
        user_id: int,
        questions: list[dict[str, Any]],
        application_id: int | None = None,
    ) -> list[dict[str, Any]]:
        timestamp = now_iso()
        saved = []
        with self.connect() as connection:
            for question in questions:
                cursor = connection.execute(
                    """
                    INSERT INTO interview_questions (
                        user_id, application_id, question, difficulty_level, source, suggested_answer,
                        keywords, confidence_score, saved, practiced, user_answer, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, '', ?, ?)
                    """,
                    (
                        user_id,
                        application_id,
                        question.get("question", ""),
                        question.get("difficulty_level", ""),
                        question.get("source", ""),
                        question.get("suggested_answer", ""),
                        _json_dumps(question.get("keywords_to_include") or question.get("keywords") or []),
                        int(question.get("confidence_score") or 0),
                        1 if question.get("saved") else 0,
                        timestamp,
                        timestamp,
                    ),
                )
                saved.append(
                    self._interview_question_from_row(
                        connection.execute(
                            "SELECT * FROM interview_questions WHERE id = ? AND user_id = ?",
                            (cursor.lastrowid, user_id),
                        ).fetchone()
                    )
                )
            self.audit(user_id, "create", "interview_questions", None, {"count": len(saved)}, connection)
        return saved

    def list_interview_questions(self, user_id: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM interview_questions WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
            return [self._interview_question_from_row(row) for row in rows]

    def update_interview_question(
        self,
        user_id: int,
        question_id: int,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        allowed = {"saved", "practiced", "user_answer", "suggested_answer"}
        updates = {key: value for key, value in data.items() if key in allowed}
        if not updates:
            return None
        columns = []
        values: list[Any] = []
        for key, value in updates.items():
            columns.append(f"{key} = ?")
            values.append(int(value) if key in {"saved", "practiced"} else value)
        columns.append("updated_at = ?")
        values.extend([now_iso(), user_id, question_id])
        with self.connect() as connection:
            cursor = connection.execute(
                f"UPDATE interview_questions SET {', '.join(columns)} WHERE user_id = ? AND id = ?",
                values,
            )
            if cursor.rowcount == 0:
                return None
            self.audit(user_id, "update", "interview_question", question_id, updates, connection)
            row = connection.execute(
                "SELECT * FROM interview_questions WHERE id = ? AND user_id = ?",
                (question_id, user_id),
            ).fetchone()
            return self._interview_question_from_row(row)

    def create_pipeline_run(self, user_id: int, data: dict[str, Any]) -> dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO pipeline_runs (
                    user_id, job_url, job_details, resume_text, statuses, ats_before,
                    ats_after, optimized_resume, suggestions, application_assist,
                    application_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    data.get("job_url", ""),
                    _json_dumps(data.get("job_details") or {}),
                    data.get("resume_text", ""),
                    _json_dumps(data.get("statuses") or {}),
                    int(data.get("ats_before") or 0),
                    int(data.get("ats_after") or 0),
                    data.get("optimized_resume", ""),
                    _json_dumps(data.get("suggestions") or []),
                    _json_dumps(data.get("application_assist") or {}),
                    data.get("application_id"),
                    timestamp,
                    timestamp,
                ),
            )
            self.audit(user_id, "create", "pipeline_run", cursor.lastrowid, {}, connection)
            return self._pipeline_run_from_row(
                connection.execute(
                    "SELECT * FROM pipeline_runs WHERE id = ? AND user_id = ?",
                    (cursor.lastrowid, user_id),
                ).fetchone()
            )

    def analytics(self, user_id: int) -> dict[str, Any]:
        applications = self.list_applications(user_id)
        resume_version_records = self.list_resume_versions(user_id)
        questions = self.list_questions(user_id)
        interview_questions = self.list_interview_questions(user_id)
        total = len(applications)
        by_status = {status: 0 for status in STATUSES}
        by_month: dict[str, int] = {}
        ats_scores = []
        ats_before_scores = []
        ats_after_scores = []
        resume_versions: dict[str, dict[str, Any]] = {}
        for application in applications:
            by_status[application["status"]] = by_status.get(application["status"], 0) + 1
            month = application["created_at"][:7]
            by_month[month] = by_month.get(month, 0) + 1
            if application["original_ats_score"]:
                ats_before_scores.append(application["original_ats_score"])
            if application["optimized_ats_score"]:
                ats_scores.append(application["optimized_ats_score"])
                ats_after_scores.append(application["optimized_ats_score"])
            version = application.get("resume_version") or "Unversioned"
            resume_versions.setdefault(version, {"count": 0, "interviews": 0, "offers": 0})
            resume_versions[version]["count"] += 1
            if application["status"] in {"interviewing", "offer"}:
                resume_versions[version]["interviews"] += 1
            if application["status"] == "offer":
                resume_versions[version]["offers"] += 1

        applied = by_status.get("applied", 0) + by_status.get("interviewing", 0) + by_status.get("offer", 0) + by_status.get("rejected", 0)
        interviews = by_status.get("interviewing", 0) + by_status.get("offer", 0)
        offers = by_status.get("offer", 0)
        before_average = round(sum(ats_before_scores) / len(ats_before_scores), 1) if ats_before_scores else 0
        after_average = round(sum(ats_after_scores) / len(ats_after_scores), 1) if ats_after_scores else 0
        return {
            "total_applications": total,
            "applications_tracked": total,
            "by_status": by_status,
            "applications_by_month": by_month,
            "average_ats_score": round(sum(ats_scores) / len(ats_scores), 1) if ats_scores else 0,
            "ats_before_average": before_average,
            "ats_after_average": after_average,
            "average_ats_improvement": round(after_average - before_average, 1) if before_average or after_average else 0,
            "response_rate": round((interviews + by_status.get("rejected", 0)) / applied * 100, 1) if applied else 0,
            "interview_conversion_rate": round(interviews / applied * 100, 1) if applied else 0,
            "offer_conversion_rate": round(offers / applied * 100, 1) if applied else 0,
            "resume_versions": resume_versions,
            "resume_version_count": len(resume_version_records),
            "answered_questions": len([question for question in questions if question["status"] == "answered"]),
            "unanswered_questions": len([question for question in questions if question["status"] == "unanswered"]),
            "interview_questions_generated": len(interview_questions),
            "practiced_questions": len([question for question in interview_questions if question["practiced"]]),
            "application_fields_ready": self.profile_fields_ready_count(user_id),
        }

    def audit_logs(self, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM audit_logs
                WHERE user_id = ? OR user_id IS NULL
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
            logs = []
            for row in rows:
                item = dict(row)
                item["metadata"] = _json_loads(item.get("metadata"), {})
                logs.append(item)
            return logs

    def _application_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["matched_skills"] = _json_loads(item.get("matched_skills"), [])
        item["missing_skills"] = _json_loads(item.get("missing_skills"), [])
        return item

    def _resume_version_by_id(
        self,
        connection: sqlite3.Connection,
        user_id: int,
        version_id: int,
    ) -> dict[str, Any]:
        row = connection.execute(
            "SELECT * FROM resume_versions WHERE id = ? AND user_id = ?",
            (version_id, user_id),
        ).fetchone()
        return self._resume_version_from_row(row)

    def _resume_version_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["keywords_added"] = _json_loads(item.get("keywords_added"), [])
        return item

    def _question_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["options"] = _json_loads(item.get("options"), [])
        return item

    def _pipeline_run_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["job_details"] = _json_loads(item.get("job_details"), {})
        item["statuses"] = _json_loads(item.get("statuses"), {})
        item["suggestions"] = _json_loads(item.get("suggestions"), [])
        item["application_assist"] = _json_loads(item.get("application_assist"), {})
        return item

    def _interview_question_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["keywords"] = _json_loads(item.get("keywords"), [])
        item["saved"] = bool(item.get("saved"))
        item["practiced"] = bool(item.get("practiced"))
        return item
