"""Helpers for injecting Detilda form scripts into HTML pages."""
from __future__ import annotations

import re
from pathlib import Path

from core import logger, utils
from core.config_loader import ConfigLoader

__all__ = ["inject_form_scripts"]


def _load_options(loader: ConfigLoader) -> tuple[str, str, str]:
    service_cfg = loader.service_files()
    options = service_cfg.get("html_inject_options", {})
    handler = str(options.get("inject_handler_script", "form-handler.js"))
    forms_script = str(options.get("inject_forms_script", "aida-forms-1.0.min.js"))
    marker = str(options.get("inject_after_marker", "</body>"))
    return handler, forms_script, marker


def inject_form_scripts(project_root: Path, loader: ConfigLoader) -> int:
    project_root = Path(project_root)
    handler, forms_script, marker = _load_options(loader)
    processed = 0

    marker_pattern = re.compile(re.escape(marker), re.IGNORECASE)
    legacy_pattern = re.compile(
        rf"<script[^>]+src=['\"]js/{re.escape(handler)}['\"][^>]*></script>",
        re.IGNORECASE,
    )

    for path in project_root.rglob("*.html"):
        try:
            content = utils.safe_read(path)
        except Exception as exc:
            logger.warn(f"[inject] Пропуск {path.name}: {exc}")
            continue

        original = content

        replacements = 0
        content, replacements = legacy_pattern.subn(
            f'<script src="js/{forms_script}"></script>', content
        )

        def _ensure_script(text: str, script_name: str) -> tuple[str, bool]:
            tag = f'\n<script src="js/{script_name}"></script>'
            if script_name in text:
                return text, False
            if marker_pattern.search(text):
                return marker_pattern.sub(tag + marker, text), True
            return text + tag, True

        content, added_forms = _ensure_script(content, forms_script)

        if content != original:
            utils.safe_write(path, content)
            processed += 1
            if replacements:
                logger.info(
                    f"🔄 Заменён скрипт {handler} → {forms_script} в {path.name}"
                )
            if added_forms:
                logger.info(f"🧩 Добавлен AIDA forms в {path.name}")

    if processed:
        logger.info(
            f"✓ Внедрение завершено. Обновлено файлов: {processed} (маркер: {marker})."
        )
    else:
        logger.info("✓ Внедрение завершено. Изменений не требуется.")
    return processed
