"""Lightweight link checker for Detilda."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from core import logger, utils
from core.config_loader import ConfigLoader

__all__ = ["LinkCheckerResult", "check_links"]


@dataclass
class LinkCheckerResult:
    checked: int = 0
    broken: int = 0


def _iter_links(text: str, patterns: Iterable[str]) -> Iterable[str]:
    for pattern in patterns:
        try:
            regex = re.compile(pattern)
        except re.error:
            logger.warn(f"[checker] Некорректный паттерн: {pattern}")
            continue
        for match in regex.finditer(text):
            link = match.groupdict().get("link")
            if link:
                yield link


def check_links(project_root: Path, loader: ConfigLoader) -> LinkCheckerResult:
    project_root = Path(project_root)
    patterns_cfg = loader.patterns()
    ignore_prefixes = tuple(patterns_cfg.get("ignore_prefixes", []))
    link_patterns = patterns_cfg.get("links", [])

    result = LinkCheckerResult()

    for file_path in utils.list_files_recursive(project_root, extensions=(".html", ".htm")):
        try:
            text = utils.safe_read(file_path)
        except Exception:
            continue
        for link in _iter_links(text, link_patterns):
            if link.startswith("/"):
                candidate = project_root / link.lstrip("/")
            else:
                candidate = (file_path.parent / link).resolve()
            if any(link.startswith(prefix) for prefix in ignore_prefixes):
                continue
            result.checked += 1
            if not candidate.exists():
                result.broken += 1
                logger.warn(
                    f"[checker] Битая ссылка в {utils.relpath(file_path, project_root)}: {link}"
                )

    logger.info(
        f"🔍 Проверка ссылок завершена. Проверено: {result.checked}, битых: {result.broken}"
    )
    return result
