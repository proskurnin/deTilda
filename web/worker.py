"""Background worker: runs pipeline in a thread pool."""
from __future__ import annotations

import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from core.api import process_archive
from core.params import ProcessParams
from web.jobs import Job, JobStatus, JobStore

_WORKDIR = Path(__file__).resolve().parents[1] / "_workdir"


def _prepare_archive(upload_path: Path, job_id: str) -> Path:
    """Repack uploaded ZIP so the root folder is named {job_id}.

    This guarantees project_root = _workdir/{job_id}/ and archive.py's
    _detect_repository_root() correctly identifies the repo root.
    """
    job_dir = _WORKDIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    dest = job_dir / f"{job_id}.zip"

    with zipfile.ZipFile(upload_path, "r") as src_zf:
        names = src_zf.namelist()
        if not names:
            raise ValueError("Архив пустой")

        # Detect the root folder in the archive (may be "site/", "mysite/", etc.)
        root_parts = {n.split("/")[0] for n in names if "/" in n}
        old_root = root_parts.pop() if len(root_parts) == 1 else None

        with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as dst_zf:
            for name in names:
                data = src_zf.read(name)
                if old_root and name.startswith(old_root + "/"):
                    new_name = job_id + name[len(old_root):]
                else:
                    new_name = job_id + "/" + name
                dst_zf.writestr(new_name, data)

    return dest


def run_job(
    job: Job,
    store: JobStore,
    upload_path: Path,
    email: str,
    logs_dir: Path,
) -> None:
    """Execute pipeline and update job state. Runs in a thread pool."""
    try:
        job.status = JobStatus.RUNNING
        store.update(job)

        archive_path = _prepare_archive(upload_path, job.id)
        stats = process_archive(
            archive_path,
            params=ProcessParams(email=email),
            logs_dir=logs_dir,
        )

        job.result_path = stats.project_root
        job.stats = {
            "renamed_assets":   stats.renamed_assets,
            "fixed_links":      stats.fixed_links,
            "broken_links":     stats.broken_links,
            "downloaded":       stats.downloaded_remote_assets,
            "forms_hooked":     stats.forms_hooked,
            "exec_time":        round(stats.exec_time, 1),
            "warnings":         stats.warnings,
            "errors":           stats.errors,
        }
        job.status = JobStatus.DONE
    except Exception as exc:
        job.status = JobStatus.ERROR
        job.error = str(exc)
    finally:
        job.finished_at = datetime.now(timezone.utc)
        store.update(job)
        # Clean up the uploaded file
        try:
            upload_path.unlink(missing_ok=True)
        except OSError:
            pass
