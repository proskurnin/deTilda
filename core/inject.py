"""Helpers for injecting Detilda form scripts into HTML pages."""
from __future__ import annotations

import re
from pathlib import Path

from core import logger, utils
from core.config_loader import ConfigLoader

__all__ = ["inject_form_scripts"]


def _load_options(loader: ConfigLoader) -> tuple[str, str, list[str], str]:
    service_cfg = loader.service_files()
    options = service_cfg.get("html_inject_options", {})
    handler = str(options.get("inject_handler_script", "form-handler.js"))
    marker = str(options.get("inject_after_marker", "</body>"))
    head_marker = str(options.get("inject_head_marker", "</head>"))
    head_scripts_raw = options.get("inject_head_scripts", ["ga.js"])
    head_scripts = (
        [script for script in head_scripts_raw if isinstance(script, str) and script.strip()]
        if isinstance(head_scripts_raw, (list, tuple))
        else ["ga.js"]
    )
    return handler, marker, head_scripts, head_marker


def inject_form_scripts(project_root: Path, loader: ConfigLoader) -> int:
    project_root = Path(project_root)
    handler, marker, head_scripts, head_marker = _load_options(loader)
    processed = 0

    marker_pattern = re.compile(re.escape(marker), re.IGNORECASE)
    head_marker_pattern = re.compile(re.escape(head_marker), re.IGNORECASE)

    for path in project_root.rglob("*.html"):
        try:
            content = utils.safe_read(path)
        except Exception as exc:
            logger.warn(f"[inject] Пропуск {path.name}: {exc}")
            continue

        original = content

        def _ensure_script(text: str, script_name: str) -> tuple[str, bool]:
            tag = f'\n<script src="js/{script_name}"></script>'
            if script_name in text:
                return text, False
            if marker_pattern.search(text):
                return marker_pattern.sub(tag + marker, text), True
            return text + tag, True

        def _ensure_head_script(text: str, script_name: str) -> tuple[str, bool]:
            tag = f'\n<script src="js/{script_name}"></script>'
            if script_name in text:
                return text, False
            if head_marker_pattern.search(text):
                return head_marker_pattern.sub(tag + head_marker, text), True
            return text, False

        head_scripts_added: list[str] = []
        for head_script in head_scripts:
            content, added = _ensure_head_script(content, head_script)
            if added:
                head_scripts_added.append(head_script)

        content, added_handler = _ensure_script(content, handler)

        if content != original:
            utils.safe_write(path, content)
            processed += 1
            for head_script in head_scripts_added:
                logger.info(f"🧩 Добавлен скрипт {head_script} в <head> ({path.name})")
            if added_handler:
                logger.info(f"🧩 Добавлен скрипт {handler} в {path.name}")

    if processed:
        logger.info(
            f"✓ Внедрение завершено. Обновлено файлов: {processed} (маркер: {marker})."
        )
    else:
        logger.info("✓ Внедрение завершено. Изменений не требуется.")
    return processed
