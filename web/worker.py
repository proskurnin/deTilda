"""Background worker: runs pipeline in a thread pool."""
from __future__ import annotations

import shutil
import traceback
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def _strip_log_prefix(line: str) -> str:
    parts = line.strip().split(" ", 3)
    if len(parts) == 4 and parts[0].count("-") == 2 and parts[1].count(":") == 2:
        return f"{parts[2]} {parts[3]}".strip()
    return line.strip()


def _collect_log_messages(logs_dir: Path, *, limit: int = 50) -> dict[str, list[str]]:
    messages: dict[str, list[str]] = {"warnings": [], "errors": []}
    if not logs_dir.exists():
        return messages

    skip_warning_fragments = (
        "Предупреждений:",
        "завершено с предупреждениями",
    )
    skip_error_fragments = ("Ошибок:",)

    for log_path in sorted(logs_dir.glob("*_detilda.log")):
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue

        for raw_line in lines:
            line = _strip_log_prefix(raw_line)
            if not line:
                continue

            is_error = "💥" in raw_line or "⛔" in raw_line or "Traceback" in raw_line or " ERROR " in raw_line
            is_warning = "⚠️" in raw_line or " WARNING " in raw_line
            if (
                is_error
                and not any(fragment in line for fragment in skip_error_fragments)
                and len(messages["errors"]) < limit
            ):
                messages["errors"].append(line)
            elif (
                is_warning
                and not any(fragment in line for fragment in skip_warning_fragments)
                and len(messages["warnings"]) < limit
            ):
                messages["warnings"].append(line)

    return messages


def _nonzero_items(items: list[tuple[str, Any]]) -> list[str]:
    return [f"{label}: {value}" for label, value in items if value not in (0, "", None, False)]


def _build_stats_details(stats: Any, logs_dir: Path) -> dict[str, dict[str, Any]]:
    log_messages = _collect_log_messages(logs_dir)

    warning_items = _nonzero_items(
        [
            ("Битых внутренних ссылок", stats.broken_links),
            ("Битых htaccess-маршрутов", stats.broken_htaccess_routes),
            ("Не удалось загрузить browser runtime assets", stats.browser_runtime_failed),
            ("Потенциально неразрешённых изображений", stats.images_unresolved),
            ("Namespace critical leftovers", stats.namespace_critical_leftovers),
            ("Namespace warning leftovers", stats.namespace_warning_leftovers),
            ("SSL bypass downloads", stats.ssl_bypassed_downloads),
        ]
    )
    warning_items.extend(log_messages["warnings"])

    error_items = log_messages["errors"]

    return {
        "renamed_assets": {
            "title": "Переименовано файлов",
            "items": _nonzero_items(
                [
                    ("Переименовано ассетов", stats.renamed_assets),
                    ("Удалено ассетов", stats.removed_assets),
                    ("Очищено файлов", stats.cleaned_files),
                    ("Отформатировано HTML-файлов", stats.formatted_html_files),
                    ("Namespace renamed paths", stats.namespace_renamed_paths),
                    ("Namespace files updated", stats.namespace_files_updated),
                ]
            ) or ["Изменений файлов не было."],
        },
        "fixed_links": {
            "title": "Исправлено ссылок",
            "items": _nonzero_items(
                [
                    ("Исправлено ссылок", stats.fixed_links),
                    ("Битых внутренних ссылок осталось", stats.broken_links),
                    ("Битых htaccess-маршрутов найдено изначально", stats.htaccess_routes_initially_broken),
                    ("Автоисправлено htaccess-маршрутов", stats.htaccess_routes_autofixed),
                    ("Битых htaccess-маршрутов осталось", stats.broken_htaccess_routes),
                ]
            ) or ["Ссылки не требовали правок."],
        },
        "downloaded": {
            "title": "Загружено с CDN",
            "items": _nonzero_items(
                [
                    ("Загружено удалённых ассетов", stats.downloaded_remote_assets),
                    ("Browser runtime pages", stats.browser_runtime_pages),
                    ("Browser runtime requests", stats.browser_runtime_requests),
                    ("Browser runtime downloads", stats.browser_runtime_downloaded),
                    ("Browser runtime failed", stats.browser_runtime_failed),
                    ("SSL bypass downloads", stats.ssl_bypassed_downloads),
                ]
            ) or ["CDN-загрузок не было."],
        },
        "forms_hooked": {
            "title": "Формы",
            "items": _nonzero_items(
                [
                    ("Форм найдено", stats.forms_found),
                    ("Форм подключено к handler", stats.forms_hooked),
                ]
            ) or ["Формы не найдены."],
        },
        "warnings": {
            "title": "Предупреждения",
            "items": warning_items or ["Предупреждений нет."],
        },
        "errors": {
            "title": "Ошибки",
            "items": error_items or ["Ошибок нет."],
        },
    }


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
            "details":        _build_stats_details(stats, logs_dir),
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
