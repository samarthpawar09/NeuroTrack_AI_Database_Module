"""
NeuroTrack AI SQLite database module.

Default database: <project_root>/database/neurotrack.db
The database file is created locally by init_db() and should not be committed to Git.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

PROJECT_DIR = Path(__file__).resolve().parent
DB_PATH = PROJECT_DIR / "database" / "neurotrack.db"
SCHEMA_PATH = PROJECT_DIR / "schema.sql"

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
_KEY_BYTES = 64



class ClosingConnection(sqlite3.Connection):

    def __exit__(self, exc_type, exc, tb):
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()


def _connect(db_path: str | os.PathLike | None = None) -> sqlite3.Connection:
    """Open and automatically close a SQLite connection."""

    path = Path(db_path) if db_path is not None else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        path,
        timeout=10,
        factory=ClosingConnection
    )

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    return conn




def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _hash_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 8:
        raise ValueError("Password must be a string of at least 8 characters.")
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N,
        r=_SCRYPT_R, p=_SCRYPT_P, dklen=_KEY_BYTES
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${derived.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against the scrypt hash returned by create_user()."""
    try:
        algorithm, n, r, p, salt_hex, expected_hex = password_hash.split("$")
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(expected_hex))
        )
        return hmac.compare_digest(actual.hex(), expected_hex)
    except (ValueError, TypeError, AttributeError):
        return False


def init_db(db_path: str | os.PathLike | None = None) -> None:
    """Create all required tables. Safe to call repeatedly."""
    schema_file = SCHEMA_PATH
    schema = schema_file.read_text(encoding="utf-8")
    with _connect(db_path) as conn:
        conn.executescript(schema)


def create_user(
    full_name: str,
    email: str,
    password: str,
    db_path: str | os.PathLike | None = None,
) -> int:
    """
    Register a user and return the new user_id.
    Raises sqlite3.IntegrityError if the email already exists.
    """
    if not full_name or not full_name.strip():
        raise ValueError("full_name is required.")
    if not email or not email.strip():
        raise ValueError("email is required.")

    password_hash = _hash_password(password)
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO users (full_name, email, password_hash, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (full_name.strip(), email.strip().lower(), password_hash, _utc_now()),
        )
        return int(cursor.lastrowid)


def get_user_by_email(
    email: str,
    db_path: str | os.PathLike | None = None,
) -> dict[str, Any] | None:
    """Return a user row (including password_hash for authentication), or None."""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT user_id, full_name, email, password_hash, created_at "
            "FROM users WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()
        return dict(row) if row else None


def _validate_uuid(value: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("assessment_id must be a valid UUID.") from exc


def save_assessment(
    user_id: int,
    assessment: dict[str, Any],
    db_path: str | os.PathLike | None = None,
) -> str:
    """
    Save the complete assessment object and all nested responses atomically.
    Expected response shape: {"domain": {"question_id": answer, ...}, ...}.
    The assessment UUID from the backend is preserved.
    """
    if not isinstance(assessment, dict):
        raise TypeError("assessment must be a dictionary.")

    assessment_id = _validate_uuid(assessment.get("assessment_id"))
    scores = assessment.get("scores")
    if not isinstance(scores, dict):
        raise ValueError("assessment.scores must be an object.")

    required_score_fields = ("total_correct", "total_questions", "percentage")
    missing = [field for field in required_score_fields if field not in scores]
    if missing:
        raise ValueError(f"Missing scores fields: {', '.join(missing)}")

    responses = assessment.get("responses", {})
    if not isinstance(responses, dict):
        raise ValueError("assessment.responses must be an object grouped by domain.")

    assessment_date = assessment.get("assessment_date") or _utc_now()
    # Require a timestamp that explicitly identifies UTC or has an offset.
    try:
        parsed_date = datetime.fromisoformat(str(assessment_date).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("assessment_date must be a valid ISO-8601 timestamp.") from exc
    if parsed_date.tzinfo is None:
        raise ValueError("assessment_date must include a timezone.")
    assessment_date = parsed_date.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    response_rows = []
    for domain, questions in responses.items():
        if not isinstance(questions, dict):
            raise ValueError(f"Responses for domain {domain!r} must be an object.")
        for question_id, answer in questions.items():
            response_rows.append(
                (assessment_id, str(question_id), str(domain),
                 json.dumps(answer, ensure_ascii=False, separators=(",", ":")))
            )

    domain_scores = scores.get("domain_scores", {})
    if domain_scores is None:
        domain_scores = {}
    status = assessment.get("status", "processed")
    if status is None:
        status = "processed"

    # A single transaction ensures assessment and response rows succeed or roll back together.
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO assessments (
                assessment_id, user_id, assessment_version, assessment_date,
                total_correct, total_questions, percentage, domain_scores, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                assessment_id,
                user_id,
                assessment.get("assessment_version"),
                assessment_date,
                int(scores["total_correct"]),
                int(scores["total_questions"]),
                float(scores["percentage"]),
                json.dumps(domain_scores, ensure_ascii=False),
                str(status),
            ),
        )
        conn.executemany(
            """
            INSERT INTO assessment_responses
                (assessment_id, question_id, domain, answer)
            VALUES (?, ?, ?, ?)
            """,
            response_rows,
        )
    return assessment_id


def get_user_assessments(
    user_id: int,
    db_path: str | os.PathLike | None = None,
) -> list[dict[str, Any]]:
    """Return assessment history for exactly the supplied user_id, newest first."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT assessment_id, user_id, assessment_version, assessment_date,
                   total_correct, total_questions, percentage, domain_scores, status
            FROM assessments
            WHERE user_id = ?
            ORDER BY assessment_date DESC, assessment_id DESC
            """,
            (user_id,),
        ).fetchall()
        results = [dict(row) for row in rows]
        for item in results:
            item["domain_scores"] = json.loads(item["domain_scores"])
        return results


def get_assessment_by_id(
    assessment_id: str,
    user_id: int,
    db_path: str | os.PathLike | None = None,
) -> dict[str, Any] | None:
    """
    Return one assessment and its responses only if it belongs to user_id.
    Requiring user_id prevents insecure cross-user access by UUID alone.
    """
    assessment_id = _validate_uuid(assessment_id)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT assessment_id, user_id, assessment_version, assessment_date,
                   total_correct, total_questions, percentage, domain_scores, status
            FROM assessments
            WHERE assessment_id = ? AND user_id = ?
            """,
            (assessment_id, user_id),
        ).fetchone()
        if row is None:
            return None

        result = dict(row)
        result["domain_scores"] = json.loads(result["domain_scores"])
        response_rows = conn.execute(
            """
            SELECT question_id, domain, answer
            FROM assessment_responses
            WHERE assessment_id = ?
            ORDER BY domain, question_id
            """,
            (assessment_id,),
        ).fetchall()

        grouped_responses: dict[str, dict[str, Any]] = {}
        for response in response_rows:
            grouped_responses.setdefault(response["domain"], {})[response["question_id"]] = (
                json.loads(response["answer"])
            )
        result["responses"] = grouped_responses
        return result
