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
                    notes, follow_up_at, applied_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            elif key in {"ats_score", "original_ats_score", "optimized_ats_score"}:
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
                INSERT INTO recruiters (user_id, name, email, phone, company, linkedin, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    data.get("name", "").strip(),
                    data.get("email", "").strip(),
                    data.get("phone", "").strip(),
                    data.get("company", "").strip(),
                    data.get("linkedin", "").strip(),
                    data.get("notes", "").strip(),
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

    def analytics(self, user_id: int) -> dict[str, Any]:
        applications = self.list_applications(user_id)
        total = len(applications)
        by_status = {status: 0 for status in STATUSES}
        by_month: dict[str, int] = {}
        ats_scores = []
        resume_versions: dict[str, dict[str, Any]] = {}
        for application in applications:
            by_status[application["status"]] = by_status.get(application["status"], 0) + 1
            month = application["created_at"][:7]
            by_month[month] = by_month.get(month, 0) + 1
            if application["optimized_ats_score"]:
                ats_scores.append(application["optimized_ats_score"])
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
        return {
            "total_applications": total,
            "by_status": by_status,
            "applications_by_month": by_month,
            "average_ats_score": round(sum(ats_scores) / len(ats_scores), 1) if ats_scores else 0,
            "response_rate": round((interviews + by_status.get("rejected", 0)) / applied * 100, 1) if applied else 0,
            "interview_conversion_rate": round(interviews / applied * 100, 1) if applied else 0,
            "offer_conversion_rate": round(offers / applied * 100, 1) if applied else 0,
            "resume_versions": resume_versions,
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
