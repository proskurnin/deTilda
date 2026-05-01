"""Script injection helpers for the deTilda pipeline.

Шаг 5 конвейера. Tilda при экспорте не знает о наших скриптах —
этот модуль вставляет их в каждый HTML-файл проекта.

Два места вставки (настраиваются в config.yaml):
  - перед </body>: form-handler.js — обработчик форм
  - перед </head>: ga-config.js + ga.js — Google Analytics (и другие head-скрипты)

Идемпотентный: если скрипт уже есть в файле — не дублирует.
Вызывается ПОСЛЕ forms.py (скрипты должны уже лежать в js/).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core import logger, utils
from core.config_loader import ConfigLoader

__all__ = ["inject_form_scripts"]


def _load_options(loader: ConfigLoader) -> tuple[str, str, list[str], str]:
    """Читает настройки инъекции из config.yaml."""
    opts = loader.service_files().html_inject_options
    # Если список head-скриптов пуст — используем GA config + loader как дефолт
    head_scripts = [s for s in opts.inject_head_scripts if s.strip()] or [
        "/js/ga-config.js",
        "/js/ga.js",
    ]
    return opts.inject_handler_script, opts.inject_after_marker, head_scripts, opts.inject_head_marker


def _resolve_inputs(context: Any, loader: ConfigLoader | None) -> tuple[Path, ConfigLoader]:
    """Принимает ProjectContext или Path+ConfigLoader — возвращает пару (path, loader)."""
    if hasattr(context, "project_root"):
        project_root = Path(context.project_root)
        resolved_loader = loader or getattr(context, "config_loader", None)
    else:
        project_root = Path(context)
        resolved_loader = loader

    if resolved_loader is None:
        raise ValueError(
            "inject_form_scripts требует loader при передаче только project_root. "
            "Передайте loader явно или используйте ProjectContext."
        )
    return project_root, resolved_loader


def _ensure_body_script(
    text: str,
    script_name: str,
    marker_pattern: re.Pattern[str],
    marker: str,
) -> tuple[str, bool]:
    """Вставляет <script src="js/{script_name}"> перед marker (обычно </body>).

    Если скрипт уже есть — не дублирует. Возвращает (новый текст, был ли добавлен).
    """
    tag = f'\n<script src="js/{script_name}"></script>'
    if script_name in text:
        return text, False
    if marker_pattern.search(text):
        return marker_pattern.sub(tag + marker, text), True
    # marker не найден — добавляем в конец файла
    return text + tag, True


def _script_src(script_name: str) -> str:
    """Return script src, preserving absolute or already-qualified paths."""
    script_name = script_name.strip()
    if script_name.startswith(("/", "http://", "https://", "//")):
        return script_name
    if "/" in script_name:
        return script_name
    return f"js/{script_name}"


def _script_already_present(text: str, script_name: str, src: str) -> bool:
    """Return True if current or legacy src form is already present."""
    candidates = {script_name.strip(), src}
    if src.startswith("/"):
        candidates.add(src.lstrip("/"))
    return any(candidate and candidate in text for candidate in candidates)


def _ensure_head_script(
    text: str,
    script_name: str,
    head_marker_pattern: re.Pattern[str],
    head_marker: str,
) -> tuple[str, bool]:
    """Вставляет head-script перед head_marker (обычно </head>).

    Если скрипт уже есть — не дублирует. Если </head> не найден — пропускает файл.
    Возвращает (новый текст, был ли добавлен).
    """
    src = _script_src(script_name)
    tag = f'\n<script defer src="{src}"></script>'
    if _script_already_present(text, script_name, src):
        return text, False
    if head_marker_pattern.search(text):
        return head_marker_pattern.sub(tag + head_marker, text), True
    return text, False


def inject_form_scripts(context: Any, loader: ConfigLoader | None = None) -> int:
    """Вставляет скрипты во все HTML-файлы проекта.

    Возвращает количество изменённых файлов.
    """
    project_root, resolved_loader = _resolve_inputs(context, loader)
    handler, marker, head_scripts, head_marker = _load_options(resolved_loader)

    marker_pattern = re.compile(re.escape(marker), re.IGNORECASE)
    head_marker_pattern = re.compile(re.escape(head_marker), re.IGNORECASE)

    processed = 0
    for path in utils.list_files_recursive(project_root, extensions=(".html",)):
        try:
            content = utils.safe_read(path)
        except Exception as exc:
            logger.warn(f"[inject] Пропуск {path.name}: {exc}")
            continue

        original = content
        head_scripts_added: list[str] = []

        # Вставляем head-скрипты (ga.js и др.) перед </head>
        for head_script in head_scripts:
            content, added = _ensure_head_script(
                content, head_script, head_marker_pattern, head_marker
            )
            if added:
                head_scripts_added.append(head_script)

        # Вставляем обработчик форм перед </body>
        content, added_handler = _ensure_body_script(
            content, handler, marker_pattern, marker
        )

        if content != original:
            utils.safe_write(path, content)
            processed += 1
            for head_script in head_scripts_added:
                logger.info(f"🧩 Добавлен скрипт {head_script} в <head> ({path.name})")
            if added_handler:
                logger.info(f"🧩 Добавлен скрипт {handler} в {path.name}")

    if processed:
        logger.info(f"✓ Внедрение завершено. Обновлено файлов: {processed} (маркер: {marker}).")
    else:
        logger.info("✓ Внедрение завершено. Изменений не требуется.")
    return processed
