"""Report generation utilities."""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Final, Iterable, Tuple

from core import logger, utils
from core.version import APP_ENTRY_POINT, APP_LICENSE, APP_PYTHON, APP_RELEASE_DATE, APP_TITLE

__all__ = ["generate_intermediate_report", "generate_final_report"]

_REPORTS_ENABLED: bool | None = None
_ENV_DISABLE_REPORTS: Final[str] = "DETILDA_DISABLE_REPORTS"


def _reports_enabled() -> bool:
    global _REPORTS_ENABLED
    if _REPORTS_ENABLED is not None:
        return _REPORTS_ENABLED

    manifest = utils.load_manifest()
    features = manifest.get("features", {}) if isinstance(manifest, dict) else {}
    enabled = True
    if isinstance(features, dict):
        enabled = bool(features.get("reports", True))

    env_override = os.getenv(_ENV_DISABLE_REPORTS)
    if env_override is not None:
        enabled = False

    _REPORTS_ENABLED = enabled
    if not _REPORTS_ENABLED:
        logger.info("[report] Генерация отчётов отключена")
    return _REPORTS_ENABLED


def _report_path(suffix: str) -> Path:
    project_name = logger.get_project_name()
    logs_dir = logger.get_logs_dir()
    return logs_dir / f"{project_name}_{suffix}.txt"


def generate_intermediate_report(
    renamed: int,
    cleaned: int,
    fixed_links: int,
    broken_links: int,
) -> None:
    if not _reports_enabled():
        logger.debug(
            "[report] Пропуск промежуточного отчёта (генерация отключена)"
        )
        return

    report_path = _report_path("detilda_report")
    text = (
        f"=== {APP_TITLE} — Промежуточный отчёт ===\n"
        f"Дата: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"{'-' * 70}\n"
        f"🖼 Переименовано ассетов: {renamed}\n"
        f"🧹 Очищено файлов: {cleaned}\n"
        f"🔗 Исправлено ссылок: {fixed_links}\n"
        f"🚫 Осталось битых ссылок: {broken_links}\n"
        f"{'-' * 70}\n"
    )
    try:
        utils.safe_write(report_path, text)
        logger.ok(f"🧾 Промежуточный отчёт сохранён: {report_path.name}")
    except Exception as exc:
        logger.err(f"💥 Ошибка при создании промежуточного отчёта: {exc}")


def generate_final_report(
    project_root: Path,
    cleaned_count: int,
    renamed_count: int,
    formatted_html_files: int,
    warnings: int,
    errors: int,
    broken_links_fixed: int,
    broken_links_left: int,
    htaccess_routes_initially_broken: int,
    htaccess_routes_autofixed: int,
    broken_htaccess_routes: int,
    downloaded_remote_assets: int,
    ssl_bypass_downloads: int,
    forms_found: int,
    forms_hooked: int,
    missing_htaccess_routes: Iterable[Tuple[str, str, str, str | None]],
    exec_time: float,
) -> None:
    if not _reports_enabled():
        logger.debug("[report] Пропуск финального отчёта (генерация отключена)")
        return

    report_path = _report_path("final_report")
    if errors > 0:
        status = f"❌ {APP_TITLE} — завершено с ошибками"
    elif warnings > 0:
        status = f"⚠️ {APP_TITLE} — завершено с предупреждениями"
    else:
        status = f"✅ {APP_TITLE} — завершено успешно"
    meta_parts = [APP_TITLE]
    if APP_RELEASE_DATE:
        meta_parts.append(f"выпуск {APP_RELEASE_DATE}")
    if APP_LICENSE:
        meta_parts.append(APP_LICENSE)
    if APP_PYTHON:
        meta_parts.append(f"Python {APP_PYTHON}")
    if APP_ENTRY_POINT:
        meta_parts.append(f"точка входа: {APP_ENTRY_POINT}")
    meta_line = " | ".join(meta_parts)

    text = (
        f"=== {APP_TITLE} — Финальный отчёт ===\n"
        f"{meta_line}\n"
        f"Проект: {project_root.name}\n"
        f"Путь: {project_root.resolve()}\n"
        f"Дата: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"{'=' * 70}\n"
        f"📦 Переименовано ассетов: {renamed_count}\n"
        f"🧹 Очищено файлов: {cleaned_count}\n"
        f"🧼 Отформатировано HTML-файлов: {formatted_html_files}\n"
        f"🌐 Загружено удалённых ассетов: {downloaded_remote_assets}\n"
        f"🔐 SSL bypass downloads: {ssl_bypass_downloads}\n"
        f"🔗 Исправлено ссылок: {broken_links_fixed}\n"
        f"❌ Битых внутренних ссылок: {broken_links_left}\n"
        f"❌ Битых htaccess-маршрутов найдено изначально: {htaccess_routes_initially_broken}\n"
        f"🛠 Автоисправлено htaccess-маршрутов: {htaccess_routes_autofixed}\n"
        f"❌ Битых htaccess-маршрутов: {broken_htaccess_routes}\n"
        f"📝 Форм найдено: {forms_found}\n"
        f"🧩 Форм подключено к handler: {forms_hooked}\n"
        f"⚠️ Предупреждений: {warnings}\n"
        f"⛔ Ошибок: {errors}\n"
        f"🕓 Время выполнения: {exec_time:.2f} сек\n"
        f"{'=' * 70}\n"
        f"{status}\n"
        f"{'=' * 70}\n"
    )
    missing_lines = list(missing_htaccess_routes)
    if missing_lines:
        text += "Потерянные htaccess-маршруты:\n"
        for alias, target, action, replacement in missing_lines:
            if replacement:
                text += f"  - {alias} -> {target} [{action}: {replacement}]\n"
            else:
                text += f"  - {alias} -> {target} [{action}]\n"
        text += f"{'=' * 70}\n"
    try:
        utils.safe_write(report_path, text)
        logger.ok(f"📊 Финальный отчёт сформирован: {report_path.name}")
    except Exception as exc:
        logger.err(f"💥 Ошибка при создании финального отчёта: {exc}")
