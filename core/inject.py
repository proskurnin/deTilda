# -*- coding: utf-8 -*-
"""
inject.py — внедрение JS-обработчиков в HTML-файлы Detilda v4.9 unified
Правила берутся из config/config.yaml → service_files.html_inject_options
и service_files.scripts_to_comment_out_tags.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from core import logger, config_loader, utils


def inject_scripts_and_handlers(project_root: str, script_dir: str | Path | None = None):
    """
    Основная функция внедрения JS-скриптов в HTML.
    Использует параметры из config/config.yaml → service_files.html_inject_options.
    """
    project_root = Path(project_root)

    cfg_service = config_loader.get_rules_service_files(script_dir)
    inject_opts = cfg_service.get("html_inject_options", {})
    scripts_to_comment = cfg_service.get("scripts_to_comment_out_tags", {}).get("filenames", [])

    inject_script_name = inject_opts.get("inject_handler_script", "form-handler.js")
    inject_after_marker = inject_opts.get("inject_after_marker", "</body>")

    logger.info("→ Внедрение form-handler.js и очистка старых скриптов...")

    processed = 0
    modified = 0

    for path in project_root.rglob("*.html"):
        try:
            content = utils.safe_read(path)
        except Exception as e:
            logger.warn(f"[inject] Пропуск {path.name}: {e}")
            continue

        new_content = content

        # --- Удаление старых тильдовских скриптов ---
        for bad_script in scripts_to_comment:
            pattern = rf'(<script[^>]+{re.escape(bad_script)}[^>]*><\/script>)'
            new_content = re.sub(pattern, r"<!-- \1 -->", new_content, flags=re.IGNORECASE)

        # --- Проверяем, есть ли уже наш обработчик ---
        if inject_script_name not in new_content:
            inject_tag = f'\n<script src="js/{inject_script_name}"></script>\n'
            pattern_marker = re.compile(re.escape(inject_after_marker), re.IGNORECASE)
            if pattern_marker.search(new_content):
                new_content = pattern_marker.sub(inject_tag + inject_after_marker, new_content)
                logger.info(f"🧩 Добавлен скрипт {inject_script_name} в {path.name}")
                modified += 1
            else:
                # если </body> не найден — добавляем в конец
                new_content += inject_tag
                logger.warn(f"[inject] В {path.name} не найден </body> — скрипт добавлен в конец.")
                modified += 1

        # --- Добавляем AIDA forms (если нет) ---
        if "aida-forms-1.0.min.js" not in new_content:
            new_content = new_content.replace(
                inject_after_marker,
                f'\n<script src="js/aida-forms-1.0.min.js"></script>\n{inject_after_marker}',
            )
            logger.info(f"🧩 Добавлен AIDA forms в {path.name}")
            modified += 1

        # --- Сохраняем, если изменилось ---
        if new_content != content:
            utils.safe_write(path, new_content)
            processed += 1

    logger.info(f"✓ Внедрение завершено. Изменено файлов: {processed}, обновлено вставок: {modified}")


# === Прямая отладка ===
if __name__ == "__main__":
    test_project = "./_workdir/project5059034"
    test_script_dir = "."
    try:
        inject_scripts_and_handlers(test_project, test_script_dir)
    except Exception as e:
        logger.err(f"💥 Ошибка в inject.py: {e}")