# -*- coding: utf-8 -*-
"""
report.py — модуль генерации отчётов Detilda v4.5 LTS unified
Формирует промежуточные и финальные текстовые отчёты внутри каталога logs/.
"""

import time
from pathlib import Path
from core import logger, utils


# === 📘 Промежуточный отчёт ===
def generate_intermediate_report(renamed: int, cleaned: int, fixed_links: int, broken_links: int):
    """
    Создаёт промежуточный отчёт после ключевых этапов пайплайна.
    """
    project_name = logger.get_project_name()
    logs_dir = logger.get_logs_dir()
    report_path = logs_dir / f"{project_name}_detilda_report.txt"

    try:
        text = (
            f"=== Detilda v4.5 LTS unified — Промежуточный отчёт ===\n"
            f"Проект: {project_name}\n"
            f"Дата: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"{'-'*70}\n"
            f"🖼 Переименовано ассетов: {renamed}\n"
            f"🧹 Очищено файлов: {cleaned}\n"
            f"🔗 Исправлено ссылок: {fixed_links}\n"
            f"🚫 Осталось битых ссылок: {broken_links}\n"
            f"{'-'*70}\n"
        )
        utils.safe_write(report_path, text)
        logger.ok(f"🧾 Промежуточный отчёт сохранён: {report_path.name}")
    except Exception as e:
        logger.err(f"💥 Ошибка при создании промежуточного отчёта: {e}")


# === 📗 Финальный отчёт ===
def generate_final_report(project_root: Path, renamed_count: int, warnings: int,
                          broken_links_fixed: int, broken_links_left: int, exec_time: float):
    """
    Генерирует финальный отчёт об обработке проекта Detilda.
    """
    project_name = logger.get_project_name()
    logs_dir = logger.get_logs_dir()
    final_report_path = logs_dir / f"{project_name}_final_report.txt"

    try:
        status = "✅ Успех" if broken_links_left == 0 else "⚠️ Частично (остались битые ссылки)"
        text = (
            f"=== Detilda v4.5 LTS unified — Финальный отчёт ===\n"
            f"Проект: {project_name}\n"
            f"Путь: {project_root.resolve()}\n"
            f"Дата генерации: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"{'='*70}\n"
            f"🖼 Переименовано ассетов: {renamed_count}\n"
            f"🔗 Исправлено ссылок: {broken_links_fixed}\n"
            f"🚫 Осталось битых ссылок: {broken_links_left}\n"
            f"⚠️ Предупреждений: {warnings}\n"
            f"🕓 Время выполнения: {exec_time:.2f} сек\n"
            f"{'='*70}\n"
            f"{status}\n"
            f"{'='*70}\n"
        )

        utils.safe_write(final_report_path, text)
        logger.ok(f"📊 Финальный отчёт сформирован: {final_report_path.name}")
    except Exception as e:
        logger.err(f"💥 Ошибка при создании финального отчёта: {e}")