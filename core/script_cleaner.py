"""Utilities for removing disallowed script tags from project files."""
from __future__ import annotations

import re
from pathlib import Path

from core import logger, utils
from core.config_loader import ConfigLoader

__all__ = ["remove_disallowed_scripts"]


def _collect_script_names(loader: ConfigLoader) -> list[str]:
    service_cfg = loader.service_files()
    removal_cfg = service_cfg.get("scripts_to_remove_from_project", {})
    names: list[str] = []
    if isinstance(removal_cfg, dict):
        for value in removal_cfg.get("filenames", []):
            if isinstance(value, str) and value.strip():
                names.append(value.strip())
    return names


# def _compile_script_patterns(script_names: list[str]) -> list[re.Pattern[str]]:
#     patterns: list[re.Pattern[str]] = []
#     for name in script_names:
#         if not name:
#             continue
#         escaped = re.escape(name)
#         pattern = re.compile(
#             "".join(
#                 [
#                     r"<script\b",  # opening tag start
#                     r"(?:(?!</script>).)*?",  # attributes or inline content before the match
#                     escaped,  # disallowed script reference
#                     r"(?:(?!</script>).)*?",  # rest of attributes or inline content
#                     r"</script>",
#                 ]
#             ),
#             re.IGNORECASE | re.DOTALL,
#         )
#         patterns.append(pattern)
#     return patterns


def _compile_script_patterns(script_names: list[str]) -> list[re.Pattern[str]]:
    """
    Создаёт набор регулярных выражений для поиска и удаления <script>-блоков,
    содержащих указанные имена файлов или сигнатуры трекеров.
    Поддерживает минифицированные, инлайн и многострочные скрипты.
    """
    patterns: list[re.Pattern[str]] = []

    for name in script_names:
        if not name:
            continue

        escaped = re.escape(name)

        # Основной шаблон: удаляет весь <script>...</script>, если внутри встречается имя
        base_pattern = re.compile(
            rf"<script\b[^>]*>[\s\S]*?{escaped}[\s\S]*?</script>",
            re.IGNORECASE,
        )
        patterns.append(base_pattern)

        # Дополнительно: если это известный трекер (aida/tilda/stat)
        # ищем по типичным маркерам даже без имени файла
        if "aida" in name.lower():
            aida_pattern = re.compile(
                r"<script\b[^>]*>[\s\S]*?(mainTracker\s*=\s*['\"]aida['\"]|aidastatscript)"
                r"[\s\S]*?</script>",
                re.IGNORECASE,
            )
            patterns.append(aida_pattern)

        if "tilda" in name.lower():
            tilda_pattern = re.compile(
                r"<script\b[^>]*>[\s\S]*?(tilda[-_]stat|tildastat|Tilda\.)"
                r"[\s\S]*?</script>",
                re.IGNORECASE,
            )
            patterns.append(tilda_pattern)

    # Удаляем блоки, начинающиеся с маркера "<!-- Stat -->" и следующим за ним скриптом
    patterns.append(
        re.compile(
            r"<!--\s*Stat\s*-->[\s\r\n]*<script\b[\s\S]*?</script>",
            re.IGNORECASE,
        )
    )

    return patterns



def remove_disallowed_scripts(project_root: Path, loader: ConfigLoader) -> int:
    """Remove script tags that reference disallowed filenames.

    Returns the number of removed script tags across all processed files.
    """

    project_root = Path(project_root)
    script_names = _collect_script_names(loader)
    if not script_names:
        return 0

    patterns_cfg = loader.patterns()
    text_extensions = tuple(patterns_cfg.get("text_extensions", [])) or (
        ".html",
        ".htm",
        ".php",
        ".js",
        ".css",
        ".txt",
    )

    script_patterns = _compile_script_patterns(script_names)

    removed_tags = 0
    updated_files = 0

    for path in utils.list_files_recursive(project_root, extensions=text_extensions):
        try:
            text = utils.safe_read(path)
        except Exception as exc:
            logger.warn(f"[script_cleaner] Пропуск {path.name}: {exc}")
            continue

        original = text
        removed_in_file = 0
        for pattern in script_patterns:
            text, count = pattern.subn("", text)
            if count:
                removed_in_file += count

        if removed_in_file and text != original:
            utils.safe_write(path, text)
            removed_tags += removed_in_file
            updated_files += 1
            logger.info(
                f"🗑 Удалены теги скриптов ({removed_in_file}) в {utils.relpath(path, project_root)}"
            )

    if removed_tags:
        logger.info(
            f"🧹 Скрипты удалены: всего {removed_tags} тегов в {updated_files} файлах."
        )
    else:
        logger.info("🧹 Скрипты для удаления не найдены.")

    return removed_tags

