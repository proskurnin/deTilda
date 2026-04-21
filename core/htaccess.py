"""Helpers for reading Apache ``.htaccess`` routing rules."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from core import logger, utils
from core.config_loader import ConfigLoader

__all__ = ["RouteInfo", "collect_htaccess_routes", "collect_routes", "get_route_info"]


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


def fix_missing_htaccess_route(
    route: str, target: str, fallback_target: str = "404.html"
) -> str:
    logger.warn(
        f"[htaccess] Маршрут {route} вёл в отсутствующий файл {target}, заменён на {fallback_target}"
    )
    return fallback_target


def _store_route(
    alias: str,
    target: str,
    project_root: Path,
    routes: Dict[str, str],
    *,
    soft_fallback_enabled: bool = False,
    fallback_target: str = "404.html",
) -> None:
    alias = _normalize_alias(alias)
    target = target.strip()
    candidate = _resolve_target_path(target, project_root)
    exists = candidate.exists() if candidate else False

    if exists:
        routes[alias] = target
        _routes_info[alias] = RouteInfo(target=target, exists=True, path=candidate)
        logger.debug(f"[htaccess] {alias} → {target} (файл есть)")
        return

    logger.err(f"[htaccess] Битый маршрут: {alias} → {target} (файл отсутствует)")

    if soft_fallback_enabled:
        fallback_candidate = _resolve_target_path(fallback_target, project_root)
        if fallback_candidate and fallback_candidate.exists():
            fixed_target = fix_missing_htaccess_route(alias, target, fallback_target)
            routes[alias] = fixed_target
            _routes_info[alias] = RouteInfo(
                target=fixed_target, exists=True, path=fallback_candidate
            )
            return

    routes[alias] = target
    _routes_info[alias] = RouteInfo(target=target, exists=False, path=candidate if candidate else None)


def _increment_stat(stats: Any | None, field: str) -> None:
    if stats is None:
        return
    if not hasattr(stats, field):
        return
    setattr(stats, field, getattr(stats, field, 0) + 1)


def collect_htaccess_routes(
    htaccess_path: Path,
    project_root: Path,
    stats: Any | None = None,
) -> Dict[str, str]:
    routes: Dict[str, str] = {}

    if not htaccess_path.exists():
        logger.info("ℹ️ .htaccess не найден, пропуск анализа маршрутов")
        return routes

    content = htaccess_path.read_text(encoding="utf-8", errors="ignore")
    pattern = re.compile(
        r"RewriteRule\s+\^?([^\s$]+)\$?\s+([^\s]+\.html)\s*\[([^\]]*)\]",
        re.IGNORECASE,
    )

    for match in pattern.finditer(content):
        route = "/" + match.group(1).lstrip("/")
        target = match.group(2).strip()
        target_path = project_root / target

        routes[route] = target
        _routes_info[route] = RouteInfo(target=target, exists=target_path.exists(), path=target_path)
        if target_path.exists():
            logger.debug(f"[htaccess] {route} → {target} (файл есть)")
        else:
            logger.error(f"[htaccess] Битый маршрут: {route} → {target} (файл отсутствует)")
            _increment_stat(stats, "broken_htaccess_routes")
            _increment_stat(stats, "errors")

    logger.info(f"🔗 Обнаружено маршрутов из htaccess: {len(routes)}")
    return routes


def collect_routes(
    project_root: Path,
    loader: ConfigLoader,
    stats: Any | None = None,
) -> Dict[str, str]:
    routes: Dict[str, str] = {}
    _routes_info.clear()
    rewrite_re, redirect_re = _load_patterns(loader)
    patterns_cfg = loader.patterns().get("htaccess_patterns", {})
    soft_fallback_enabled = bool(patterns_cfg.get("soft_fallback_to_404", False))
    fallback_target = str(patterns_cfg.get("fallback_target", "404.html"))

    for file_path in _iter_htaccess_files(project_root):
        parsed_routes = collect_htaccess_routes(file_path, project_root, stats=stats)
        routes.update(parsed_routes)
        try:
            text = utils.safe_read(file_path)
        except Exception as exc:
            logger.warn(f"[htaccess] Не удалось прочитать {file_path}: {exc}")
            continue

        for match in rewrite_re.finditer(text):
            alias, target = match.groups()
            _store_route(
                alias,
                target,
                project_root,
                routes,
                soft_fallback_enabled=soft_fallback_enabled,
                fallback_target=fallback_target,
            )

        for match in redirect_re.finditer(text):
            alias, target = match.groups()
            _store_route(
                alias,
                target,
                project_root,
                routes,
                soft_fallback_enabled=soft_fallback_enabled,
                fallback_target=fallback_target,
            )

        index_match = re.search(r"DirectoryIndex\s+([^\s]+\.html)", text, re.IGNORECASE)
        if index_match:
            _store_route(
                "/",
                index_match.group(1),
                project_root,
                routes,
                soft_fallback_enabled=soft_fallback_enabled,
                fallback_target=fallback_target,
            )

    if routes:
        logger.info(f"🔗 Обнаружено маршрутов из htaccess: {len(routes)}")
    else:
        logger.warn("⚠️ В htaccess не найдено RewriteRule.")
    return routes


def get_route_info(alias: str) -> Optional[RouteInfo]:
    """Return stored information about a specific alias from ``.htaccess``."""

    return _routes_info.get(_normalize_alias(alias))
