"""Form asset generation for the deTilda pipeline.

Шаг 4 конвейера. Копирует готовые обработчики форм из resources/ в проект:

  - send_email.php    → корень проекта
  - js/form-handler.js → папка js/ проекта

send_email.php — универсальный, без настройки:
  - получатель определяется автоматически по домену сервера: info@<домен>
  - в dev-режиме (localhost) письма идут на тестовый адрес
  - в prod-режиме ставит BCC на страховочные адреса

При копировании константа TEST_RECIPIENTS подменяется значением из
forms.test_recipients в config.yaml — чтобы каждый проект мог иметь
свой адрес для smoke-теста (Name=Test → письмо уходит на этот адрес).

Вызывается ДО inject.py — inject подключит form-handler.js в HTML.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from core import logger, utils
from core.config_loader import ConfigLoader

__all__ = ["generate_send_email_php", "generate_form_handler_js"]

# Папка с шаблонами: core/../resources/
_RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"

# Регекс на блок `const TEST_RECIPIENTS = [...];` — подменяется на
# сгенерированный из конфига при копировании в проект.
_TEST_RECIPIENTS_BLOCK_RE = re.compile(
    r"const\s+TEST_RECIPIENTS\s*=\s*\[[^\]]*\]\s*;",
    re.DOTALL,
)


def _resolve_project_root(project_root: Path | Any) -> Path:
    """Принимает ProjectContext или Path — возвращает Path к корню проекта."""
    if hasattr(project_root, "project_root"):
        return Path(getattr(project_root, "project_root"))
    return Path(project_root)


def _resolve_config_loader(project_root: Path | Any) -> ConfigLoader | None:
    """Достаёт ConfigLoader из ProjectContext если он есть."""
    loader = getattr(project_root, "config_loader", None)
    return loader if isinstance(loader, ConfigLoader) else None


def _render_test_recipients_block(recipients: Iterable[str]) -> str:
    items = [r.strip() for r in recipients if r and r.strip()]
    if not items:
        return ""
    body = ",\n".join(f"    {json.dumps(item)}" for item in items)
    return f"const TEST_RECIPIENTS = [\n{body},\n];"


def _patch_test_recipients(template: str, recipients: Iterable[str]) -> str:
    """Подменяет блок const TEST_RECIPIENTS = [...]; в шаблоне send_email.php.

    Если recipients пусто или маркер не найден — шаблон возвращается без изменений
    (фолбэк на дефолт из resources/send_email.php).
    """
    block = _render_test_recipients_block(recipients)
    if not block:
        return template
    new_text, count = _TEST_RECIPIENTS_BLOCK_RE.subn(block, template, count=1)
    if not count:
        logger.warn(
            "[forms] В шаблоне send_email.php не найден const TEST_RECIPIENTS — "
            "значение из конфига не применено"
        )
        return template
    return new_text


def generate_send_email_php(project_root: Path | Any) -> Path:
    """Копирует resources/send_email.php в корень проекта.

    Если передан ProjectContext с config_loader, подставляет
    forms.test_recipients из конфига в const TEST_RECIPIENTS шаблона.
    Сразу после копирования вызывает generate_form_handler_js —
    оба файла нужны вместе для корректной работы форм.
    """
    resolved_root = _resolve_project_root(project_root)
    target = resolved_root / "send_email.php"
    template_path = _RESOURCES_DIR / "send_email.php"
    template = template_path.read_text(encoding="utf-8")

    # Email из params (веб-запрос) имеет приоритет над config.yaml
    params_email = getattr(getattr(project_root, "params", None), "email", "")
    if params_email:
        template = _patch_test_recipients(template, [params_email])
    else:
        loader = _resolve_config_loader(project_root)
        if loader is not None:
            template = _patch_test_recipients(template, loader.forms().test_recipients)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(template, encoding="utf-8")
    logger.info(f"📨 Файл send_email.php создан: {utils.relpath(target, resolved_root)}")
    generate_form_handler_js(resolved_root)
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
