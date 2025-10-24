"""Text cleanup helpers."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from core import logger, utils
from core.config_loader import ConfigLoader

__all__ = ["CleanStats", "clean_text_files"]


@dataclass
class CleanStats:
    updated: int = 0


def _compile_patterns(patterns: Iterable[str]) -> list[re.Pattern[str]]:
    compiled: list[re.Pattern[str]] = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern, re.IGNORECASE))
        except re.error:
            logger.warn(f"[cleaners] Некорректный паттерн: {pattern}")
    return compiled


def _apply_substitutions(text: str, substitutions: list[tuple[re.Pattern[str], str]]) -> tuple[str, bool]:
    changed = False
    for pattern, replacement in substitutions:
        new_text, count = pattern.subn(replacement, text)
        if count:
            changed = True
            text = new_text
    return text, changed


def _clean_file(
    project_root: Path,
    path: Path,
    remove_patterns: list[re.Pattern[str]],
    substitutions: list[tuple[re.Pattern[str], str]],
    generic_patterns: list[re.Pattern[str]],
) -> bool:
    try:
        text = utils.safe_read(path)
    except Exception as exc:
        logger.warn(f"[cleaners] Пропуск {path.name}: {exc}")
        return False

    original = text
    for pattern in remove_patterns:
        text = pattern.sub("", text)

    for pattern in generic_patterns:
        text = pattern.sub("", text)

    text, changed = _apply_substitutions(text, substitutions)
    if text != original or changed:
        utils.safe_write(path, text)
        logger.info(f"🧹 Очищен файл: {utils.relpath(path, project_root)}")
        return True
    return False


def _iter_targets(project_root: Path, candidates: Iterable[str]) -> Iterable[Path]:
    for name in candidates:
        path = project_root / name
        if path.exists():
            yield path


def clean_text_files(project_root: Path, loader: ConfigLoader) -> CleanStats:
    project_root = Path(project_root)
    patterns_cfg = loader.patterns()
    service_cfg = loader.service_files()

    robots_patterns = _compile_patterns(patterns_cfg.get("robots_cleanup_patterns", []))
    generic_patterns = _compile_patterns(patterns_cfg.get("tilda_remnants_patterns", []))

    readme_substitutions: list[tuple[re.Pattern[str], str]] = []
    for item in patterns_cfg.get("readme_cleanup_patterns", []):
        if isinstance(item, dict):
            pattern = item.get("pattern")
            replacement = item.get("replacement", "")
            if isinstance(pattern, str):
                try:
                    readme_substitutions.append((re.compile(pattern, re.IGNORECASE), str(replacement)))
                except re.error:
                    logger.warn(f"[cleaners] Некорректный паттерн readme: {pattern}")
        elif isinstance(item, str):
            try:
                readme_substitutions.append((re.compile(item, re.IGNORECASE), ""))
            except re.error:
                logger.warn(f"[cleaners] Некорректный паттерн readme: {item}")

    files_to_clean = service_cfg.get("cleaner_options", {}).get("files_to_clean_tilda_refs", [])
    stats = CleanStats()

    for path in _iter_targets(project_root, files_to_clean):
        remove_list = robots_patterns if path.name.lower() == "robots.txt" else []
        substitutions = readme_substitutions if path.name.lower() == "readme.txt" else []
        if _clean_file(project_root, path, remove_list, substitutions, generic_patterns):
            stats.updated += 1

    return stats
