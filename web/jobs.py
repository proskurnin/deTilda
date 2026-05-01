"""Job store for async processing queue."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, Optional


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass
class Job:
    id: str
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    result_path: Optional[Path] = None
    error: Optional[str] = None        # user-friendly message
    error_code: Optional[str] = None   # machine-readable key
    error_detail: Optional[str] = None # raw exception (admin only)
    stats: Optional[dict] = None
    progress: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "error": self.error,
            "error_code": self.error_code,
            "stats": self.stats,
            "progress": self.progress,
        }

    def to_admin_dict(self) -> dict:
        d = self.to_dict()
        d["error_detail"] = self.error_detail
        d["result_available"] = bool(self.result_path and self.result_path.exists())
        return d

    def _to_persist_dict(self) -> dict:
        d = self.to_admin_dict()
        d["result_path"] = str(self.result_path) if self.result_path else None
        d["progress"] = self.progress
        return d

    @classmethod
    def _from_persist_dict(cls, data: dict) -> "Job":
        return cls(
            id=data["id"],
            status=JobStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            finished_at=datetime.fromisoformat(data["finished_at"]) if data.get("finished_at") else None,
            result_path=Path(data["result_path"]) if data.get("result_path") else None,
            error=data.get("error"),
            error_code=data.get("error_code"),
            error_detail=data.get("error_detail"),
            stats=data.get("stats"),
            progress=data.get("progress", []),
        )


class JobStore:
    def __init__(self, persist_dir: Optional[Path] = None) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()
        self._persist_dir = persist_dir
        self._db_path = persist_dir / "jobs.sqlite3" if persist_dir is not None else None

    def _ensure_db(self) -> None:
        if self._db_path is None:
            return
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL
                )
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")

    def _save_to_sqlite(self, job: Job) -> None:
        if self._db_path is None:
            return
        self._ensure_db()
        payload = json.dumps(job._to_persist_dict(), ensure_ascii=False)
        with sqlite3.connect(self._db_path) as con:
            con.execute(
                """
                INSERT INTO jobs (id, payload, created_at, finished_at, status)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload = excluded.payload,
                    created_at = excluded.created_at,
                    finished_at = excluded.finished_at,
                    status = excluded.status
                """,
                (
                    job.id,
                    payload,
                    job.created_at.isoformat(),
                    job.finished_at.isoformat() if job.finished_at else None,
                    job.status.value,
                ),
            )

    def _load_from_sqlite(self) -> list[Job]:
        if self._db_path is None or not self._db_path.exists():
            return []
        self._ensure_db()
        jobs: list[Job] = []
        with sqlite3.connect(self._db_path) as con:
            rows = con.execute("SELECT payload FROM jobs ORDER BY created_at DESC").fetchall()
        for (payload,) in rows:
            try:
                jobs.append(Job._from_persist_dict(json.loads(payload)))
            except Exception:
                pass
        return jobs

    def _save(self, job: Job) -> None:
        if self._persist_dir is None:
            return
        try:
            self._save_to_sqlite(job)
        except (OSError, sqlite3.Error):
            pass

    def _load_legacy_json_jobs(self) -> list[Job]:
        """Load jobs from the pre-SQLite JSON persistence format."""
        if self._persist_dir is None:
            return []
        jobs: list[Job] = []
        for p in self._persist_dir.glob("*.json"):
            try:
                jobs.append(Job._from_persist_dict(json.loads(p.read_text(encoding="utf-8"))))
            except Exception:
                pass
        return jobs

    def restore(self) -> int:
        """Load jobs persisted to disk. Called once on app startup."""
        if self._persist_dir is None:
            return 0
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        loaded = 0
        jobs_by_id = {job.id: job for job in self._load_from_sqlite()}
        for job in self._load_legacy_json_jobs():
            jobs_by_id.setdefault(job.id, job)
        for job in jobs_by_id.values():
            try:
                # Jobs still marked running/pending at startup had their process killed —
                # mark them as errors so the store reflects reality.
                if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
                    job.status = JobStatus.ERROR
                    job.error = "Прервано перезапуском сервера"
                    job.finished_at = job.finished_at or datetime.now(timezone.utc)
                    self._save(job)
                with self._lock:
                    self._jobs[job.id] = job
                self._save(job)
                loaded += 1
            except Exception:
                pass
        return loaded

    def create(self) -> Job:
        job = Job(id=str(uuid.uuid4()))
        with self._lock:
            self._jobs[job.id] = job
        self._save(job)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.id] = job
        self._save(job)

    def expire_old(self, ttl_minutes: int) -> list:
        """Forget expired results from memory while keeping admin history in SQLite."""
        cutoff = datetime.now(timezone.utc)
        with self._lock:
            to_delete = [
                jid for jid, j in self._jobs.items()
                if j.finished_at and (cutoff - j.finished_at).total_seconds() > ttl_minutes * 60
            ]
            for jid in to_delete:
                self._jobs.pop(jid, None)
        return to_delete

    def active_count(self) -> int:
        with self._lock:
            return sum(
                1 for j in self._jobs.values()
                if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
            )

    def list_all(self) -> list:
        if self._db_path is not None:
            try:
                return self._load_from_sqlite()
            except (OSError, sqlite3.Error):
                pass
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
