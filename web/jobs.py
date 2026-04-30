"""Job store for async processing queue."""
from __future__ import annotations

import json
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
    error: Optional[str] = None
    stats: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "error": self.error,
            "stats": self.stats,
        }

    def _to_persist_dict(self) -> dict:
        d = self.to_dict()
        d["result_path"] = str(self.result_path) if self.result_path else None
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
            stats=data.get("stats"),
        )


class JobStore:
    def __init__(self, persist_dir: Optional[Path] = None) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()
        self._persist_dir = persist_dir

    def _save(self, job: Job) -> None:
        if self._persist_dir is None:
            return
        try:
            path = self._persist_dir / f"{job.id}.json"
            path.write_text(json.dumps(job._to_persist_dict()), encoding="utf-8")
        except OSError:
            pass

    def _delete_file(self, job_id: str) -> None:
        if self._persist_dir is None:
            return
        try:
            (self._persist_dir / f"{job_id}.json").unlink(missing_ok=True)
        except OSError:
            pass

    def restore(self) -> int:
        """Load jobs persisted to disk. Called once on app startup."""
        if self._persist_dir is None or not self._persist_dir.exists():
            return 0
        loaded = 0
        for p in self._persist_dir.glob("*.json"):
            try:
                job = Job._from_persist_dict(json.loads(p.read_text(encoding="utf-8")))
                # Jobs still marked running/pending at startup had their process killed —
                # mark them as errors so the store reflects reality.
                if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
                    job.status = JobStatus.ERROR
                    job.error = "Прервано перезапуском сервера"
                    job.finished_at = job.finished_at or datetime.now(timezone.utc)
                with self._lock:
                    self._jobs[job.id] = job
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
        """Remove finished jobs older than ttl_minutes. Returns list of expired job IDs."""
        cutoff = datetime.now(timezone.utc)
        with self._lock:
            to_delete = [
                jid for jid, j in self._jobs.items()
                if j.finished_at and (cutoff - j.finished_at).total_seconds() > ttl_minutes * 60
            ]
            for jid in to_delete:
                self._jobs.pop(jid, None)
        for jid in to_delete:
            self._delete_file(jid)
        return to_delete

    def active_count(self) -> int:
        with self._lock:
            return sum(
                1 for j in self._jobs.values()
                if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
            )

    def list_all(self) -> list:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
