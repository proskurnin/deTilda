"""Form asset generation for the deTilda pipeline.

Шаг 4 конвейера. Копирует готовые обработчики форм из resources/ в проект:

  - send_email.php    → корень проекта
  - js/form-handler.js → папка js/ проекта

send_email.php — универсальный, без настройки:
  - получатель определяется автоматически по домену сервера: info@<домен>
  - в dev-режиме (localhost) письма идут на тестовый адрес
  - в prod-режиме ставит BCC на страховочные адреса

Вызывается ДО inject.py — inject подключит form-handler.js в HTML.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core import logger, utils

__all__ = ["generate_send_email_php", "generate_form_handler_js"]

# Папка с шаблонами: core/../resources/
_RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"


def _resolve_project_root(project_root: Path | Any) -> Path:
    """Принимает ProjectContext или Path — возвращает Path к корню проекта."""
    if hasattr(project_root, "project_root"):
        return Path(getattr(project_root, "project_root"))
    return Path(project_root)


def generate_send_email_php(project_root: Path | Any) -> Path:
    """Копирует resources/send_email.php в корень проекта.

    Сразу после копирования вызывает generate_form_handler_js —
    оба файла нужны вместе для корректной работы форм.
    """
    project_root = _resolve_project_root(project_root)
    target = project_root / "send_email.php"
    template_path = _RESOURCES_DIR / "send_email.php"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(template_path.read_bytes())
    logger.info(f"📨 Файл send_email.php создан: {utils.relpath(target, project_root)}")
    generate_form_handler_js(project_root)
    return target


def generate_form_handler_js(project_root: Path | Any) -> Path:
    """Копирует resources/js/form-handler.js в js/ проекта."""
    project_root = _resolve_project_root(project_root)
    target = project_root / "js" / "form-handler.js"
    template_path = _RESOURCES_DIR / "js" / "form-handler.js"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(template_path.read_bytes())
    logger.info(f"📨 Файл form-handler.js создан: {utils.relpath(target, project_root)}")
    return target
