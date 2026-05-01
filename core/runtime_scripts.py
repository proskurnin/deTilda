"""Shared rules for preserving/removing runtime script files."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from core import utils

__all__ = [
    "CONDITIONALLY_REQUIRED_RUNTIME_SCRIPTS",
    "filter_removable_scripts",
    "project_needs_media_runtime",
]

_MEDIA_MARKERS_RE = re.compile(
    r"("
    r"youtube\.com|youtu\.be|data-youtube|(?:t|ai)-video|(?:t|ai)-slds|(?:t|ai)-gallery|"
    r"data-img-zoom-url|data-original|(?:t|ai)-bgimg|"
    r"<form\b|js-form-proccess|data-formactiontype|data-tooltip-hook=[\"']#popup|"
    r"\bt-popup\b|\bai-popup\b|\bt702\b|\bai702\b"
    r")",
    re.IGNORECASE,
)

CONDITIONALLY_REQUIRED_RUNTIME_SCRIPTS = {
    "tilda-events-1.0.min.js",
    "aida-events-1.0.min.js",
    "tilda-fallback-1.0.min.js",
    "aida-fallback-1.0.min.js",
    "tilda-forms-1.0.min.js",
    "aida-forms-1.0.min.js",
}


def project_needs_media_runtime(project_root: Path) -> bool:
    """Return True when pages contain blocks that need Tilda runtime scripts.

    The name is kept for compatibility. Besides media/lazyload blocks, popup
    forms need Tilda form/events runtime for visual initialization; the custom
    form-handler.js replaces submission, not the block UI runtime.
    """

    for path in utils.list_files_recursive(project_root, extensions=(".html", ".htm")):
        try:
            text = utils.safe_read(path)
        except Exception:
            continue
        if _MEDIA_MARKERS_RE.search(text):
            return True
    return False


def filter_removable_scripts(
    script_names: Iterable[str],
    project_root: Path,
) -> tuple[list[str], list[str]]:
    """Split configured script names into removable and preserved subsets."""

    normalized = [name.strip() for name in script_names if isinstance(name, str) and name.strip()]
    if not normalized:
        return [], []
    if not project_needs_media_runtime(project_root):
        return normalized, []

    removable = [
        name for name in normalized if name.lower() not in CONDITIONALLY_REQUIRED_RUNTIME_SCRIPTS
    ]
    preserved = [name for name in normalized if name not in removable]
    return removable, preserved
