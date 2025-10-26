"""Utilities for removing disallowed script tags from project files."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

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


_SCRIPT_OPEN_RE = re.compile(r"<script\b", re.IGNORECASE)
_SCRIPT_CLOSE_RE = re.compile(r"</script\s*>", re.IGNORECASE)
_SRC_ATTR_RE = re.compile(
    r"\bsrc\s*=\s*(?:" +
    r'"([^"\\>]*)"' +
    r"|'([^'\\>]*)'" +
    r"|([^>\s]+))",
    re.IGNORECASE,
)


def _normalize_src(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    # Отбрасываем параметры и якори, оставляем только имя файла.
    normalized = value.split("#", 1)[0].split("?", 1)[0]
    normalized = normalized.replace("\\", "/")
    return normalized.rsplit("/", 1)[-1].lower()


def _iter_script_blocks(text: str) -> Iterator[tuple[int, int, str, str]]:
    """Итерируется по срезам <script>...</script> в тексте."""

    pos = 0
    while True:
        match = _SCRIPT_OPEN_RE.search(text, pos)
        if not match:
            break

        start = match.start()
        tag_start = match.end()
        tag_close_index = text.find(">", tag_start)
        if tag_close_index == -1:
            break

        tag_close = tag_close_index + 1
        start_tag = text[start:tag_close]
        # Самозакрывающийся тег (<script ... />)
        if start_tag.rstrip().endswith("/>"):
            yield start, tag_close, start_tag, start_tag
            pos = tag_close
            continue

        end_match = _SCRIPT_CLOSE_RE.search(text, tag_close)
        if not end_match:
            pos = tag_close
            continue

        end = end_match.end()
        block = text[start:end]
        yield start, end, block, start_tag
        pos = end



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

    removed_tags = 0
    updated_files = 0
    lowered_names = [name.lower() for name in script_names]
    names_lookup = set(lowered_names)

    for path in utils.list_files_recursive(project_root, extensions=text_extensions):
        try:
            text = utils.safe_read(path)
        except Exception as exc:
            logger.warn(f"[script_cleaner] Пропуск {path.name}: {exc}")
            continue

        original = text
        removed_in_file = 0
        pieces: list[str] = []
        last_index = 0

        for start, end, block, start_tag in _iter_script_blocks(original):
            remove_block = False

            match = _SRC_ATTR_RE.search(start_tag)
            normalized_src = ""
            if match:
                src_value = next((group for group in match.groups() if group), "")
                normalized_src = _normalize_src(src_value)

            if normalized_src and normalized_src in names_lookup:
                remove_block = True
            elif extra_patterns and any(pattern.search(block) for pattern in extra_patterns):
                remove_block = True

            if remove_block:
                pieces.append(original[last_index:start])
                last_index = end
                removed_in_file += 1

        if removed_in_file:
            pieces.append(original[last_index:])
            text = "".join(pieces)
        elif script_names:
            lowered_text = original.lower()
            matched_names = [
                name for name, lowered in zip(script_names, lowered_names) if lowered in lowered_text
            ]
            if matched_names:
                logger.debug(
                    "[script_cleaner] Найдены упоминания скриптов, но src не совпадает: "
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

