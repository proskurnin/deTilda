"""HTML formatting stage for final project output."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core import logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.project import ProjectContext
from core import utils

_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}

_RAW_BLOCK_RE = re.compile(
    r"<(script|style|pre|textarea)\b[^>]*>.*?</\1\s*>",
    flags=re.IGNORECASE | re.DOTALL,
)

_OPEN_TAG_RE = re.compile(r"^<([a-zA-Z][a-zA-Z0-9:-]*)\b[^>]*>$")
_CLOSE_TAG_RE = re.compile(r"^</([a-zA-Z][a-zA-Z0-9:-]*)\s*>$")


def _iter_targets(project_root: Path) -> list[Path]:
    return sorted(utils.list_files_recursive(project_root, extensions=(".html", ".htm")))


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _mask_raw_blocks(text: str) -> tuple[str, dict[str, str]]:
    replacements: dict[str, str] = {}

    def _replace(match: re.Match[str]) -> str:
        token = f"__DETILDA_RAW_BLOCK_{len(replacements)}__"
        replacements[token] = match.group(0)
        return token

    return _RAW_BLOCK_RE.sub(_replace, text), replacements


def _split_tag_boundaries(text: str) -> str:
    # Split only on whitespace between tags to avoid changing meaningful text nodes.
    return re.sub(r">\s*<", ">\n<", text)


def _is_self_closing(tag_text: str) -> bool:
    return tag_text.endswith("/>")


def _restore_raw_blocks(text: str, replacements: dict[str, str]) -> str:
    for token, original in replacements.items():
        text = text.replace(token, original)
    return text


def _normalize_pretty_html(text: str) -> str:
    normalized = _normalize_newlines(text)
    masked, raw_blocks = _mask_raw_blocks(normalized)
    split = _split_tag_boundaries(masked)

    lines = split.split("\n")
    pretty: list[str] = []
    indent = 0

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if pretty and pretty[-1] != "":
                pretty.append("")
            continue

        close_match = _CLOSE_TAG_RE.match(line)
        if close_match:
            indent = max(0, indent - 1)

        pretty.append(f"{'  ' * indent}{line}")

        open_match = _OPEN_TAG_RE.match(line)
        if open_match:
            tag_name = open_match.group(1).lower()
            if (
                not _is_self_closing(line)
                and tag_name not in _VOID_TAGS
                and not re.search(rf"</{re.escape(tag_name)}\s*>", line, flags=re.IGNORECASE)
            ):
                indent += 1

    result = "\n".join(pretty).strip("\n") + "\n"
    return _restore_raw_blocks(result, raw_blocks)


def run(context: "ProjectContext", stats: Any | None = None) -> int:
    targets = _iter_targets(context.project_root)
    formatted = 0

    for path in targets:
        rel_path = utils.relpath(path, context.project_root)
        try:
            original = utils.safe_read(path)
            updated = _normalize_pretty_html(original)
            if updated != _normalize_newlines(original):
                utils.safe_write(path, updated)
                formatted += 1
                logger.info(f"🧼 HTML приведён в порядок: {rel_path}")
        except Exception as exc:
            logger.err(f"[html_prettify] Ошибка форматирования {rel_path}: {exc}")
            if stats is not None and hasattr(stats, "errors"):
                stats.errors += 1

    if stats is not None and hasattr(stats, "formatted_html_files"):
        stats.formatted_html_files = getattr(stats, "formatted_html_files", 0) + formatted
    logger.info(f"[html_prettify] ✅ Завершено. Отформатировано файлов: {formatted}")
    return formatted
