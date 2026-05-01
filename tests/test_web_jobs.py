"""Tests for persistent web job history."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from web.jobs import JobStatus, JobStore


def test_job_store_restores_sqlite_history(tmp_path) -> None:
    store = JobStore(persist_dir=tmp_path)
    job = store.create()
    job.status = JobStatus.DONE
    job.finished_at = datetime.now(timezone.utc)
    job.stats = {"fixed_links": 3}
    store.update(job)

    restored = JobStore(persist_dir=tmp_path)
    assert restored.restore() == 1

    jobs = restored.list_all()
    assert len(jobs) == 1
    assert jobs[0].id == job.id
    assert jobs[0].status == JobStatus.DONE
    assert jobs[0].stats == {"fixed_links": 3}


def test_expire_old_keeps_admin_history_in_sqlite(tmp_path) -> None:
    store = JobStore(persist_dir=tmp_path)
    job = store.create()
    job.status = JobStatus.DONE
    job.finished_at = datetime.now(timezone.utc) - timedelta(hours=2)
    store.update(job)

    expired = store.expire_old(ttl_minutes=30)

    assert expired == [job.id]
    assert store.get(job.id) is None
    assert [j.id for j in store.list_all()] == [job.id]


def test_restore_marks_interrupted_jobs_as_errors(tmp_path) -> None:
    store = JobStore(persist_dir=tmp_path)
    job = store.create()
    job.status = JobStatus.RUNNING
    store.update(job)

    restored = JobStore(persist_dir=tmp_path)
    restored.restore()

    restored_job = restored.get(job.id)
    assert restored_job is not None
    assert restored_job.status == JobStatus.ERROR
    assert restored_job.error == "Прервано перезапуском сервера"
    assert restored_job.finished_at is not None
