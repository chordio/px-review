from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReviewJob:
    delivery_id: str
    dedupe_key: str
    installation_id: int
    repository: str
    pull_number: int
    expected_head_sha: str | None
    trigger: str
    attempts: int = 0


class JobStore:
    """A durable, single-service queue. Use Postgres before running many replicas."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS review_jobs (
                    delivery_id TEXT PRIMARY KEY,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    available_at REAL NOT NULL,
                    last_error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            # A process crash can leave a job running. Requeue on startup; GitHub
            # delivery and head-SHA deduplication keep the external effect bounded.
            db.execute(
                "UPDATE review_jobs SET status='pending', updated_at=? "
                "WHERE status='running'",
                (time.time(),),
            )

    def enqueue(self, job: ReviewJob) -> bool:
        now = time.time()
        payload = json.dumps(asdict(job))
        with self._connect() as db:
            cursor = db.execute(
                """
                INSERT OR IGNORE INTO review_jobs
                (delivery_id, dedupe_key, payload, status, attempts, available_at,
                 created_at, updated_at)
                VALUES (?, ?, ?, 'pending', 0, ?, ?, ?)
                """,
                (job.delivery_id, job.dedupe_key, payload, now, now, now),
            )
            return cursor.rowcount == 1

    def claim_next(self) -> ReviewJob | None:
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                """
                SELECT * FROM review_jobs
                WHERE status='pending' AND available_at <= ?
                ORDER BY created_at
                LIMIT 1
                """,
                (now,),
            ).fetchone()
            if row is None:
                db.commit()
                return None
            attempts = int(row["attempts"]) + 1
            db.execute(
                "UPDATE review_jobs SET status='running', attempts=?, updated_at=? "
                "WHERE delivery_id=?",
                (attempts, now, row["delivery_id"]),
            )
            db.commit()
        payload = json.loads(row["payload"])
        payload["attempts"] = attempts
        return ReviewJob(**payload)

    def complete(self, delivery_id: str) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE review_jobs SET status='complete', updated_at=? "
                "WHERE delivery_id=?",
                (time.time(), delivery_id),
            )

    def fail(self, job: ReviewJob, error: str, *, max_attempts: int = 3) -> None:
        terminal = job.attempts >= max_attempts
        delay = min(60, 2 ** max(1, job.attempts))
        with self._connect() as db:
            db.execute(
                """
                UPDATE review_jobs
                SET status=?, available_at=?, last_error=?, updated_at=?
                WHERE delivery_id=?
                """,
                (
                    "failed" if terminal else "pending",
                    time.time() if terminal else time.time() + delay,
                    error[:4000],
                    time.time(),
                    job.delivery_id,
                ),
            )

    def stats(self) -> dict[str, int]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT status, COUNT(*) AS count FROM review_jobs GROUP BY status"
            ).fetchall()
        return {str(row["status"]): int(row["count"]) for row in rows}

