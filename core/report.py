"""Report generation utilities."""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Final

from core import logger, utils

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
        "=== Detilda v4.5.0 LTS unified — Промежуточный отчёт ===\n"
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
    renamed_count: int,
    warnings: int,
    broken_links_fixed: int,
    broken_links_left: int,
    exec_time: float,
) -> None:
    if not _reports_enabled():
        logger.debug("[report] Пропуск финального отчёта (генерация отключена)")
        return

    report_path = _report_path("final_report")
    status = "✅ Успех" if broken_links_left == 0 else "⚠️ Есть проблемы"
    text = (
        "=== Detilda v4.5.0 LTS unified — Финальный отчёт ===\n"
        f"Проект: {project_root.name}\n"
        f"Путь: {project_root.resolve()}\n"
        f"Дата: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"{'=' * 70}\n"
        f"🖼 Переименовано ассетов: {renamed_count}\n"
        f"🔗 Исправлено ссылок: {broken_links_fixed}\n"
        f"🚫 Осталось битых ссылок: {broken_links_left}\n"
        f"⚠️ Предупреждений: {warnings}\n"
        f"🕓 Время выполнения: {exec_time:.2f} сек\n"
        f"{'=' * 70}\n"
        f"{status}\n"
        f"{'=' * 70}\n"
    )
    try:
        utils.safe_write(report_path, text)
        logger.ok(f"📊 Финальный отчёт сформирован: {report_path.name}")
    except Exception as exc:
        logger.err(f"💥 Ошибка при создании финального отчёта: {exc}")
