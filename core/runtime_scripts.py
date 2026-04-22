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
    r"(youtube\.com|youtu\.be|data-youtube|t-video|t-slds|t-gallery|data-img-zoom-url|data-original|t-bgimg)",
    re.IGNORECASE,
)

CONDITIONALLY_REQUIRED_RUNTIME_SCRIPTS = {
    "tilda-events-1.0.min.js",
    "aida-events-1.0.min.js",
    "tilda-fallback-1.0.min.js",
    "aida-fallback-1.0.min.js",
}


def project_needs_media_runtime(project_root: Path) -> bool:
    """Return ``True`` when pages contain media blocks that need runtime scripts."""

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
