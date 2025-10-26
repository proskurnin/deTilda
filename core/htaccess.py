"""Helpers for reading Apache ``.htaccess`` routing rules."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from core import logger, utils
from core.config_loader import ConfigLoader

__all__ = ["RouteInfo", "collect_routes", "get_route_info"]


@dataclass(frozen=True)
class RouteInfo:
    """Information about a single route discovered in ``.htaccess``."""

    target: str
    exists: bool
    path: Optional[Path] = None


_routes_info: Dict[str, RouteInfo] = {}


def _load_patterns(loader: ConfigLoader) -> tuple[re.Pattern[str], re.Pattern[str]]:
    patterns_cfg = loader.patterns().get("htaccess_patterns", {})
    rewrite_re = re.compile(
        patterns_cfg.get(
            "rewrite_rule",
            r"(?im)^[ \t]*RewriteRule[ \t]+\^/?([a-z0-9\-_/]+)\??\$?[ \t]+([^ \t]+)",
        )
    )
    redirect_re = re.compile(
        patterns_cfg.get(
            "redirect",
            r"(?im)^[ \t]*Redirect(?:Permanent|[ \t]+3\d{2})?[ \t]+(/[^ \t]+)[ \t]+([^ \t]+)",
        )
    )
    return rewrite_re, redirect_re


def _iter_htaccess_files(project_root: Path) -> list[Path]:
    result: list[Path] = []
    for name in (".htaccess", "htaccess"):
        path = project_root / name
        if path.exists():
            result.append(path)
    return result


def _normalize_alias(alias: str) -> str:
    alias = alias.strip()
    if not alias:
        return "/"
    alias = alias.strip("/")
    return f"/{alias}" if alias else "/"


def _resolve_target_path(target: str, project_root: Path) -> Optional[Path]:
    target = target.strip()
    if not target:
        return None
    if "$" in target:
        return None
    if any(target.startswith(prefix) for prefix in ("http://", "https://", "//")):
        return None

    clean_target = target.split("?", 1)[0].split("#", 1)[0].strip()
    if not clean_target:
        return None

    raw_path = clean_target.lstrip("/") if clean_target.startswith("/") else clean_target
    try:
        candidate = (project_root / raw_path).resolve()
    except Exception:
        return None

    try:
        project_root_resolved = project_root.resolve()
    except Exception:
        project_root_resolved = project_root
    if candidate != project_root_resolved and project_root_resolved not in candidate.parents:
        return None
    return candidate


def _store_route(alias: str, target: str, project_root: Path, routes: Dict[str, str]) -> None:
    alias = _normalize_alias(alias)
    target = target.strip()
    routes[alias] = target
    candidate = _resolve_target_path(target, project_root)
    exists = candidate.exists() if candidate else False
    _routes_info[alias] = RouteInfo(target=target, exists=exists, path=candidate if candidate else None)
    existence_note = "есть" if exists else "нет"
    logger.debug(f"[htaccess] {alias} → {target} (файл {existence_note})")


def collect_routes(project_root: Path, loader: ConfigLoader) -> Dict[str, str]:
    routes: Dict[str, str] = {}
    _routes_info.clear()
    rewrite_re, redirect_re = _load_patterns(loader)

    for file_path in _iter_htaccess_files(project_root):
        try:
            text = utils.safe_read(file_path)
        except Exception as exc:
            logger.warn(f"[htaccess] Не удалось прочитать {file_path}: {exc}")
            continue

        for match in rewrite_re.finditer(text):
            alias, target = match.groups()
            _store_route(alias, target, project_root, routes)

        for match in redirect_re.finditer(text):
            alias, target = match.groups()
            _store_route(alias, target, project_root, routes)

        index_match = re.search(r"DirectoryIndex\s+([^\s]+\.html)", text, re.IGNORECASE)
        if index_match:
            _store_route("/", index_match.group(1), project_root, routes)

    if routes:
        logger.info(f"🔗 Обнаружено маршрутов из htaccess: {len(routes)}")
    else:
        logger.warn("⚠️ В htaccess не найдено RewriteRule.")
    return routes


def get_route_info(alias: str) -> Optional[RouteInfo]:
    """Return stored information about a specific alias from ``.htaccess``."""

    return _routes_info.get(_normalize_alias(alias))
