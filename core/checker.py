"""Lightweight link checker for Detilda."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from core import logger, utils
from core.config_loader import ConfigLoader
from core.htaccess import collect_routes, get_route_info

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


def _strip_cache_busting_param(link: str) -> str:
    """Return *link* without the ``t`` query parameter and fragment."""

    split = urlsplit(link)
    filtered_params = [
        (key, value)
        for key, value in parse_qsl(split.query, keep_blank_values=True)
        if key.lower() != "t"
    ]
    sanitized_query = urlencode(filtered_params, doseq=True)
    return urlunsplit((split.scheme, split.netloc, split.path, sanitized_query, ""))


def _get_effective_base_directory(file_path: Path, project_root: Path) -> Path:
    """Return a directory to use as a base for resolving relative links."""

    stem = file_path.stem
    if not stem.endswith("body"):
        return file_path.parent

    base_name = stem[:-4]
    if not base_name:
        return file_path.parent

    project_root = project_root.resolve()
    current_dir = file_path.parent.resolve()

    candidate_filenames: list[str] = []
    suffix = file_path.suffix
    if suffix and suffix.lower().startswith(".htm"):
        candidate_filenames.append(base_name + suffix)
    for alt_suffix in (".html", ".htm"):
        candidate = base_name + alt_suffix
        if candidate not in candidate_filenames:
            candidate_filenames.append(candidate)

    while True:
        try:
            current_dir.relative_to(project_root)
        except ValueError:
            break

        for candidate_name in candidate_filenames:
            candidate_path = current_dir / candidate_name
            if candidate_path.is_file():
                return candidate_path.parent

        for match in current_dir.glob(f"{base_name}.htm*"):
            if match.is_file():
                return match.parent

        if current_dir == project_root:
            break
        current_dir = current_dir.parent

    return file_path.parent


def check_links(project_root: Path, loader: ConfigLoader) -> LinkCheckerResult:
    project_root = Path(project_root)
    patterns_cfg = loader.patterns()
    ignore_prefixes = tuple(patterns_cfg.get("ignore_prefixes", []))
    link_patterns = patterns_cfg.get("links", [])

    result = LinkCheckerResult()
    collect_routes(project_root, loader)

    for file_path in utils.list_files_recursive(project_root, extensions=(".html", ".htm")):
        try:
            text = utils.safe_read(file_path)
        except Exception:
            continue
        base_directory = _get_effective_base_directory(file_path, project_root)

        for link in _iter_links(text, link_patterns):
            normalized_link = _strip_cache_busting_param(link)
            if not normalized_link:
                continue

            link_parts = urlsplit(normalized_link)
            link_path = link_parts.path

            if any(normalized_link.startswith(prefix) for prefix in ignore_prefixes):
                continue

            if link.startswith("/"):
                route_info = get_route_info(link_path or normalized_link)
                if route_info and route_info.exists and route_info.path is not None:
                    candidate = route_info.path
                else:
                    candidate = project_root / (link_path or normalized_link).lstrip("/")
            else:
                candidate = (base_directory / (link_path or normalized_link)).resolve()
            result.checked += 1
            if not candidate.exists():
                result.broken += 1
                logger.warn(
                    f"[checker] Битая ссылка в {utils.relpath(file_path, project_root)}: {normalized_link}"
                )

    logger.info(
        f"🔍 Проверка ссылок завершена. Проверено: {result.checked}, битых: {result.broken}"
    )
    return result
