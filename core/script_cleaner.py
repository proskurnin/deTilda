"""Utilities for removing disallowed script tags from project files."""
from __future__ import annotations

import re
from pathlib import Path

from core import logger, utils
from core.config_loader import ConfigLoader

__all__ = ["remove_disallowed_scripts"]


def _collect_script_rules(loader: ConfigLoader) -> tuple[list[str], list[re.Pattern[str]]]:
    """Return script names and additional regex patterns from the config."""

    service_cfg = loader.service_files()
    removal_cfg = service_cfg.get("scripts_to_remove_from_project", {})

    names: list[str] = []
    patterns: list[re.Pattern[str]] = []

    if not isinstance(removal_cfg, dict):
        return names, patterns

    # Collect filenames (we will treat them as substrings when compiling regexes).
    for value in removal_cfg.get("filenames", []):
        if isinstance(value, str) and value.strip():
            names.append(value.strip())

    # Allow optional raw regex patterns in config for edge cases.
    for raw_pattern in removal_cfg.get("patterns", []):
        if not isinstance(raw_pattern, str) or not raw_pattern.strip():
            continue
        try:
            compiled = re.compile(raw_pattern.strip(), re.IGNORECASE)
        except re.error as exc:
            logger.warn(
                "[script_cleaner] Некорректный паттерн в конфиге scripts_to_remove_from_project: "
                f"{raw_pattern!r} ({exc})"
            )
            continue
        patterns.append(compiled)

    # Preserve ordering but remove duplicates to avoid redundant regex replacements.
    deduped_names = list(dict.fromkeys(names))

    return deduped_names, patterns


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


def _compile_script_patterns(
    script_names: list[str], extra_patterns: list[re.Pattern[str]]
) -> list[re.Pattern[str]]:
    """
    Создаёт набор регулярных выражений для поиска и удаления <script>-блоков,
    содержащих указанные имена файлов или сигнатуры трекеров.
    Поддерживает минифицированные, инлайн и многострочные скрипты.
    """
    patterns: list[re.Pattern[str]] = list(extra_patterns)

    for name in script_names:
        if not name:
            continue

        escaped = re.escape(name)

        # Основной шаблон: удаляет весь <script>...</script>, если внутри встречается имя
        # или оно присутствует в атрибутах (например, src=".../aida-forms-1.0.min.js")
        base_pattern = re.compile(
            rf"<script\b(?=[^>]*{escaped}|[^>]*>[\s\S]*?{escaped})[^>]*>[\s\S]*?</script>",
            re.IGNORECASE,
        )
        patterns.append(base_pattern)

        # На случай самозакрывающихся тегов (<script ... />) c запрещённым именем
        self_closing_pattern = re.compile(
            r"<script\b[^>]*" + escaped + r"[^>]*/>",
            re.IGNORECASE,
        )
        patterns.append(self_closing_pattern)

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
    script_names, extra_patterns = _collect_script_rules(loader)
    if not script_names and not extra_patterns:
        logger.info("[script_cleaner] Список скриптов для удаления пуст — пропуск шага.")
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

    logger.info(
        f"[script_cleaner] Используем конфиг: {loader.config_path}"
    )
    logger.info(
        "[script_cleaner] Файловые расширения для проверки: "
        + ", ".join(text_extensions)
    )
    logger.info(
        "[script_cleaner] Скрипты для удаления (из config.yaml): "
        + (", ".join(script_names) if script_names else "—")
    )
    if extra_patterns:
        logger.info(
            f"[script_cleaner] Доп. паттерны для удаления: {len(extra_patterns)}"
        )

    script_patterns = _compile_script_patterns(script_names, extra_patterns)
    logger.debug(
        f"[script_cleaner] Скомпилировано регулярных выражений: {len(script_patterns)}"
    )

    removed_tags = 0
    updated_files = 0
    lowered_names = [name.lower() for name in script_names]

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

        if not removed_in_file and script_names:
            lowered_text = original.lower()
            matched_names = [
                name
                for name, lowered in zip(script_names, lowered_names)
                if lowered in lowered_text
            ]
            if matched_names:
                logger.debug(
                    "[script_cleaner] Найдены упоминания скриптов, но паттерн не сработал: "
                    f"{matched_names} в {utils.relpath(path, project_root)}"
                )

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

