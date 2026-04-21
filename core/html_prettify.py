"""HTML formatting stage for final project output."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core import logger
from core.project import ProjectContext
from core import utils

try:
    from lxml import etree, html
except Exception:  # pragma: no cover - optional dependency resolution
    etree = None  # type: ignore[assignment]
    html = None  # type: ignore[assignment]


def _iter_targets(project_root: Path) -> list[Path]:
    root_html = sorted(path for path in project_root.glob("*.html") if path.is_file())
    body_html = []
    files_dir = project_root / "files"
    if files_dir.exists():
        body_html = sorted(path for path in files_dir.glob("*body.html") if path.is_file())
    return root_html + body_html


def _normalize_pretty_html(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    compact: list[str] = []
    previous_blank = False
    for line in lines:
        is_blank = line.strip() == ""
        if is_blank and previous_blank:
            continue
        compact.append(line)
        previous_blank = is_blank
    result = "\n".join(compact).strip("\n") + "\n"
    return result


def _extract_doctype(text: str) -> str | None:
    match = re.match(r"(?is)^\s*(<!doctype[^>]*>)", text)
    if match:
        return match.group(1)
    return None


def _prettify_html(text: str) -> str:
    if etree is None or html is None:
        raise RuntimeError("lxml не установлен")
    parser = html.HTMLParser(encoding="utf-8", recover=True, remove_comments=False)
    tree = html.document_fromstring(text, parser=parser)
    doctype = _extract_doctype(text)
    pretty = etree.tostring(
        tree,
        method="html",
        pretty_print=True,
        encoding="unicode",
        doctype=doctype,
    )
    return _normalize_pretty_html(pretty)


def run(context: ProjectContext, stats: Any | None = None) -> int:
    logger.info("[html_prettify] ▶️ Начало работы")
    formatted = 0
    for path in _iter_targets(context.project_root):
        rel_path = utils.relpath(path, context.project_root)
        try:
            original = utils.safe_read(path)
            updated = _prettify_html(original)
            if updated != original.replace("\r\n", "\n").replace("\r", "\n"):
                utils.safe_write(path, updated)
                formatted += 1
                logger.info(f"🧼 HTML приведён в порядок: {rel_path}")
        except Exception as exc:
            logger.err(f"[html_prettify] Ошибка форматирования {rel_path}: {exc}")
            if stats is not None:
                if hasattr(stats, "errors"):
                    stats.errors += 1
    if stats is not None and hasattr(stats, "formatted_html_files"):
        stats.formatted_html_files = getattr(stats, "formatted_html_files", 0) + formatted
    logger.info(f"[html_prettify] ✅ Завершено. Отформатировано файлов: {formatted}")
    return formatted
