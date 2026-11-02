"""Local SQLite storage for applicant records and review history."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4


@contextmanager
def _connect(database_path: Path) -> Iterator[sqlite3.Connection]:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database(database_path: Path) -> None:
    """Create the local application and review-history tables if needed."""
    with _connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL,
                previous_job_role TEXT NOT NULL,
                latest_job_role TEXT NOT NULL,
                job_title TEXT NOT NULL,
                experience_range TEXT NOT NULL,
                work_mode TEXT NOT NULL,
                responsibilities TEXT NOT NULL,
                job_description TEXT NOT NULL,
                required_skills_json TEXT NOT NULL,
                preferred_skills_json TEXT NOT NULL,
                applied_at_utc TEXT NOT NULL,
                retention_until_utc TEXT NOT NULL,
                match_signal_percent INTEGER,
                ats_readiness_percent INTEGER,
                review_status TEXT NOT NULL,
                reviewer_note TEXT NOT NULL DEFAULT '',
                reviewed_at_utc TEXT,
                resume_text TEXT
            );
            CREATE INDEX IF NOT EXISTS applications_applied_at_idx
                ON applications(applied_at_utc);
            CREATE INDEX IF NOT EXISTS applications_job_status_idx
                ON applications(job_title, review_status);
            CREATE TABLE IF NOT EXISTS review_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                application_id INTEGER NOT NULL REFERENCES applications(id),
                timestamp_utc TEXT NOT NULL,
                previous_status TEXT,
                new_status TEXT NOT NULL,
                reviewer_note TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS review_history_application_idx
                ON review_history(application_id, timestamp_utc);
            """
        )


def create_application(
    database_path: Path,
    applicant: dict[str, str],
    job: dict[str, Any],
    resume_text: str | None,
) -> dict[str, Any]:
    """Persist an application and return it with a stable candidate ID."""
    now = datetime.now(timezone.utc)
    applied_at = now.isoformat(timespec="seconds")
    retention_until = (now + timedelta(days=365)).isoformat(timespec="seconds")
    with _connect(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO applications (
                candidate_id, full_name, email, previous_job_role, latest_job_role,
                job_title, experience_range, work_mode, responsibilities,
                job_description, required_skills_json, preferred_skills_json,
                applied_at_utc, retention_until_utc, review_status, resume_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"pending-{uuid4().hex}",
                applicant["full_name"].strip(),
                applicant["email"].strip().casefold(),
                applicant["previous_job_role"].strip(),
                applicant["latest_job_role"].strip(),
                job["title"],
                job["experience_range"],
                job["work_mode"],
                job["responsibilities"],
                job["description"],
                json.dumps(job["required_skills"]),
                json.dumps(job["preferred_skills"]),
                applied_at,
                retention_until,
                "Needs review",
                resume_text,
            ),
        )
        application_id = cursor.lastrowid
        candidate_id = f"Candidate {application_id:06d}"
        connection.execute(
            "UPDATE applications SET candidate_id = ? WHERE id = ?",
            (candidate_id, application_id),
        )
        connection.execute(
            """
            INSERT INTO review_history (
                application_id, timestamp_utc, previous_status, new_status, reviewer_note
            ) VALUES (?, ?, NULL, ?, '')
            """,
            (application_id, applied_at, "Needs review"),
        )
        row = connection.execute(
            "SELECT * FROM applications WHERE id = ?", (application_id,)
        ).fetchone()
    if row is None:
        raise RuntimeError("The application was saved but could not be read back.")
    return dict(row)


def application_exists(database_path: Path, email: str, job_title: str) -> bool:
    """Check for an existing record; used to avoid re-adding demo profiles."""
    with _connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT 1 FROM applications
            WHERE email = ? AND job_title = ?
            LIMIT 1
            """,
            (email.strip().casefold(), job_title),
        ).fetchone()
    return row is not None


def update_application_scores(
    database_path: Path,
    candidate_id: str,
    match_signal_percent: int,
    ats_readiness_percent: int,
) -> None:
    with _connect(database_path) as connection:
        existing = connection.execute(
            "SELECT id FROM applications WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
        if existing is None:
            raise ValueError(f"No stored application exists for {candidate_id}.")
        connection.execute(
            """
            UPDATE applications
            SET match_signal_percent = ?, ats_readiness_percent = ?
            WHERE candidate_id = ? AND match_signal_percent IS NULL
            """,
            (match_signal_percent, ats_readiness_percent, candidate_id),
        )


def update_review(
    database_path: Path,
    candidate_id: str,
    new_status: str,
    reviewer_note: str,
) -> dict[str, Any]:
    """Update an application status and append an immutable status-history entry."""
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect(database_path) as connection:
        row = connection.execute(
            "SELECT id, review_status FROM applications WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"No stored application exists for {candidate_id}.")
        connection.execute(
            """
            UPDATE applications
            SET review_status = ?, reviewer_note = ?, reviewed_at_utc = ?
            WHERE id = ?
            """,
            (new_status, reviewer_note, timestamp, row["id"]),
        )
        connection.execute(
            """
            INSERT INTO review_history (
                application_id, timestamp_utc, previous_status, new_status, reviewer_note
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (row["id"], timestamp, row["review_status"], new_status, reviewer_note),
        )
        updated = connection.execute(
            "SELECT * FROM applications WHERE id = ?", (row["id"],)
        ).fetchone()
    if updated is None:
        raise RuntimeError(f"The updated application {candidate_id} could not be read back.")
    return dict(updated)


def list_applications(database_path: Path) -> list[dict[str, Any]]:
    with _connect(database_path) as connection:
        rows = connection.execute(
            "SELECT * FROM applications ORDER BY applied_at_utc DESC, id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def list_review_history(database_path: Path) -> list[dict[str, Any]]:
    with _connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT applications.candidate_id, applications.full_name,
                   applications.job_title, review_history.timestamp_utc,
                   review_history.previous_status, review_history.new_status,
                   review_history.reviewer_note
            FROM review_history
            JOIN applications ON applications.id = review_history.application_id
            ORDER BY review_history.timestamp_utc DESC, review_history.id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]
