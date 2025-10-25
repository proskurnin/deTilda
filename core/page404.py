"""Utilities to normalize the project 404 page."""
from __future__ import annotations

import re
from pathlib import Path

from core import logger, utils

__all__ = ["update_404_page"]


_TITLE_PATTERN = re.compile(r"(<title\b[^>]*>)(.*?)(</title>)", re.IGNORECASE | re.DOTALL)
_AIDA_LINK_PATTERN = re.compile(
    r"<a\b[^>]*href=[\"']https://aida\.cc[\"'][^>]*>.*?</a>",
    re.IGNORECASE | re.DOTALL,
)
_SCRIPT_PATTERN = re.compile(r"<script\b[^>]*>[\s\S]*?</script>", re.IGNORECASE)


def update_404_page(project_root: Path) -> bool:
    """Apply the requested cleanup rules to ``404.html`` if it exists."""

    project_root = Path(project_root)
    page_path = project_root / "404.html"

    if not page_path.exists():
        return False

    try:
        original = utils.safe_read(page_path)
    except Exception as exc:  # pragma: no cover - log and skip problematic files
        logger.warn(f"[404] Не удалось прочитать 404.html: {exc}")
        return False

    text = original
    changed = False

    def _title_replacer(match: re.Match[str]) -> str:
        nonlocal changed
        before = match.group(2)
        if before.strip() != "Page 404, oooops...":
            changed = True
        return f"{match.group(1)}Page 404, oooops...{match.group(3)}"

    text, title_count = _TITLE_PATTERN.subn(_title_replacer, text)
    if not title_count:
        # Если тега title нет, добавляем его внутри <head>.
        text, inserted = re.subn(
            r"(<head\b[^>]*>)",
            r"\1<title>Page 404, oooops...</title>",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
        if inserted:
            changed = True

    text, anchor_count = _AIDA_LINK_PATTERN.subn(
        "<h1>404</h1><p>Page not found, oooops...</p>", text
    )
    if anchor_count:
        changed = True

    text, script_count = _SCRIPT_PATTERN.subn("", text)
    if script_count:
        changed = True

    if changed and text != original:
        utils.safe_write(page_path, text)
        logger.info("🛠 Обновлена страница 404.html")
        return True

    return False
