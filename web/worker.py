"""Background worker: runs pipeline in a thread pool."""
from __future__ import annotations

import shutil
import traceback
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from core.api import process_archive
from core.params import ProcessParams
from web.jobs import Job, JobStatus, JobStore

_WORKDIR = Path(__file__).resolve().parents[1] / "_workdir"


def _prepare_archive(upload_path: Path, job_id: str) -> Path:
    """Repack uploaded ZIP so the root folder is named {job_id}."""
    job_dir = _WORKDIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    dest = job_dir / f"{job_id}.zip"

    with zipfile.ZipFile(upload_path, "r") as src_zf:
        names = src_zf.namelist()
        if not names:
            raise ValueError("empty_archive")

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


# Maps error_code → (user message, hint)
_ERROR_MESSAGES: dict[str, tuple[str, str]] = {
    "invalid_zip": (
        "Файл повреждён или не является ZIP-архивом.",
        "Скачайте архив заново через Tilda: Настройки сайта → Экспорт → Скачать.",
    ),
    "empty_archive": (
        "Архив пустой — файлы не найдены.",
        "Убедитесь что экспортировали полный сайт, а не отдельную страницу.",
    ),
    "unpack_failed": (
        "Не удалось распаковать архив.",
        "Проверьте что загружен ZIP-экспорт Tilda, а не другой архив.",
    ),
    "pipeline_error": (
        "Ошибка при обработке сайта.",
        "Попробуйте загрузить архив снова. Если ошибка повторяется — обратитесь в поддержку.",
    ),
    "unknown": (
        "Внутренняя ошибка сервера.",
        "Попробуйте позже или обратитесь в поддержку.",
    ),
}


def _set_error(job: Job, code: str, detail: str) -> None:
    msg, hint = _ERROR_MESSAGES.get(code, _ERROR_MESSAGES["unknown"])
    job.error_code = code
    job.error = msg
    job.error_detail = detail


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

        try:
            archive_path = _prepare_archive(upload_path, job.id)
        except zipfile.BadZipFile as exc:
            _set_error(job, "invalid_zip", str(exc))
            job.status = JobStatus.ERROR
            return
        except ValueError as exc:
            code = str(exc) if str(exc) in _ERROR_MESSAGES else "pipeline_error"
            _set_error(job, code, str(exc))
            job.status = JobStatus.ERROR
            return

        def _on_step(step: str) -> None:
            job.progress.append(step)
            store.update(job)

        try:
            stats = process_archive(
                archive_path,
                params=ProcessParams(email=email),
                logs_dir=logs_dir,
                on_step_done=_on_step,
            )
        except RuntimeError as exc:
            code = "unpack_failed" if "распаковать" in str(exc) else "pipeline_error"
            _set_error(job, code, str(exc))
            job.status = JobStatus.ERROR
            return

        job.result_path = stats.project_root
        job.stats = {
            "renamed_assets": stats.renamed_assets,
            "fixed_links":    stats.fixed_links,
            "broken_links":   stats.broken_links,
            "downloaded":     stats.downloaded_remote_assets,
            "forms_hooked":   stats.forms_hooked,
            "exec_time":      round(stats.exec_time, 1),
            "warnings":       stats.warnings,
            "errors":         stats.errors,
        }
        job.status = JobStatus.DONE

    except Exception as exc:
        _set_error(job, "unknown", traceback.format_exc())
        job.status = JobStatus.ERROR
    finally:
        job.finished_at = datetime.now(timezone.utc)
        store.update(job)
        try:
            upload_path.unlink(missing_ok=True)
        except OSError:
            pass
