"""Helpers for reading Apache ``.htaccess`` routing rules."""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from core import logger, utils
from core.config_loader import ConfigLoader

__all__ = [
    "MissingRouteInfo",
    "RouteInfo",
    "collect_htaccess_routes",
    "collect_routes",
    "get_missing_routes",
    "get_route_info",
]


@dataclass(frozen=True)
class RouteInfo:
    """Information about a single route discovered in ``.htaccess``."""

    target: str
    exists: bool
    path: Optional[Path] = None


@dataclass(frozen=True)
class MissingRouteInfo:
    """Information about routes that pointed to non-existent targets."""

    alias: str
    target: str
    action: str
    replacement: Optional[str] = None


_routes_info: Dict[str, RouteInfo] = {}
_missing_routes: List[MissingRouteInfo] = []
_missing_route_keys: set[tuple[str, str]] = set()


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


def _create_route_stub(
    alias: str,
    target: str,
    project_root: Path,
    fallback_target: str,
) -> bool:
    target_candidate = _resolve_target_path(target, project_root)
    if target_candidate is None:
        logger.warn(
            f"[htaccess] Маршрут {alias}: невозможно создать заглушку для динамической цели {target}"
        )
        return False
    fallback_candidate = _resolve_target_path(fallback_target, project_root)
    if fallback_candidate is None or not fallback_candidate.exists():
        logger.warn(
            f"[htaccess] Маршрут {alias}: не найден шаблон заглушки {fallback_target}"
        )
        return False
    try:
        target_candidate.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fallback_candidate, target_candidate)
        logger.warn(
            f"[htaccess] Маршрут {alias}: создана заглушка {target} из {fallback_target}"
        )
        return True
    except Exception as exc:
        logger.warn(
            f"[htaccess] Маршрут {alias}: не удалось создать заглушку {target}: {exc}"
        )
        return False


def _store_route(
    alias: str,
    target: str,
    project_root: Path,
    routes: Dict[str, str],
    *,
    soft_fallback_enabled: bool = False,
    fallback_target: str = "404.html",
    auto_stub_enabled: bool = False,
    stats: Any | None = None,
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

    route_key = (alias, target)
    is_new_missing = route_key not in _missing_route_keys
    if is_new_missing:
        _missing_route_keys.add(route_key)
        logger.err(f"[htaccess] Битый маршрут: {alias} → {target} (файл отсутствует)")

    if auto_stub_enabled and _create_route_stub(alias, target, project_root, fallback_target):
        stub_candidate = _resolve_target_path(target, project_root)
        routes[alias] = target
        _routes_info[alias] = RouteInfo(target=target, exists=True, path=stub_candidate)
        if is_new_missing:
            _missing_routes.append(
                MissingRouteInfo(
                    alias=alias,
                    target=target,
                    action="stub_created",
                    replacement=target,
                )
            )
            _increment_stat(stats, "broken_htaccess_routes")
        return

    if soft_fallback_enabled:
        fallback_candidate = _resolve_target_path(fallback_target, project_root)
        if fallback_candidate and fallback_candidate.exists():
            fixed_target = fix_missing_htaccess_route(alias, target, fallback_target)
            routes[alias] = fixed_target
            _routes_info[alias] = RouteInfo(
                target=fixed_target, exists=True, path=fallback_candidate
            )
            if is_new_missing:
                _missing_routes.append(
                    MissingRouteInfo(
                        alias=alias,
                        target=target,
                        action="fallback_redirect",
                        replacement=fixed_target,
                    )
                )
                _increment_stat(stats, "broken_htaccess_routes")
            return

    routes[alias] = target
    _routes_info[alias] = RouteInfo(target=target, exists=False, path=candidate if candidate else None)
    if is_new_missing:
        _missing_routes.append(
            MissingRouteInfo(alias=alias, target=target, action="unresolved", replacement=None)
        )
        _increment_stat(stats, "broken_htaccess_routes")
        _increment_stat(stats, "errors")


def _increment_stat(stats: Any | None, field: str) -> None:
    if stats is None:
        return
    if not hasattr(stats, field):
        return
    setattr(stats, field, getattr(stats, field, 0) + 1)


def _extract_alias_target(match: re.Match[str]) -> tuple[str, str] | None:
    groups = match.groups()
    if len(groups) < 2:
        return None
    alias = groups[0]
    target = groups[-1]
    if alias is None or target is None:
        return None
    return alias, target


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
            logger.debug(
                f"[htaccess] Потенциально битый маршрут: {route} → {target} (проверка в основном парсере)"
            )

    logger.info(f"🔗 Обнаружено маршрутов из htaccess: {len(routes)}")
    return routes


def collect_routes(
    project_root: Path,
    loader: ConfigLoader,
    stats: Any | None = None,
) -> Dict[str, str]:
    routes: Dict[str, str] = {}
    _routes_info.clear()
    _missing_routes.clear()
    _missing_route_keys.clear()
    rewrite_re, redirect_re = _load_patterns(loader)
    patterns_cfg = loader.patterns().get("htaccess_patterns", {})
    soft_fallback_enabled = bool(patterns_cfg.get("soft_fallback_to_404", False))
    auto_stub_enabled = bool(patterns_cfg.get("auto_stub_missing_routes", False))
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
            extracted = _extract_alias_target(match)
            if extracted is None:
                logger.warn("[htaccess] Пропущено RewriteRule: не удалось извлечь alias/target")
                continue
            alias, target = extracted
            _store_route(
                alias,
                target,
                project_root,
                routes,
                soft_fallback_enabled=soft_fallback_enabled,
                fallback_target=fallback_target,
                auto_stub_enabled=auto_stub_enabled,
                stats=stats,
            )

        for match in redirect_re.finditer(text):
            extracted = _extract_alias_target(match)
            if extracted is None:
                logger.warn("[htaccess] Пропущено Redirect: не удалось извлечь alias/target")
                continue
            alias, target = extracted
            _store_route(
                alias,
                target,
                project_root,
                routes,
                soft_fallback_enabled=soft_fallback_enabled,
                fallback_target=fallback_target,
                auto_stub_enabled=auto_stub_enabled,
                stats=stats,
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
                auto_stub_enabled=auto_stub_enabled,
                stats=stats,
            )

    if routes:
        logger.info(f"🔗 Обнаружено маршрутов из htaccess: {len(routes)}")
    else:
        logger.warn("⚠️ В htaccess не найдено RewriteRule.")
    return routes


def get_route_info(alias: str) -> Optional[RouteInfo]:
    """Return stored information about a specific alias from ``.htaccess``."""

    return _routes_info.get(_normalize_alias(alias))


def get_missing_routes() -> list[MissingRouteInfo]:
    """Return collected broken/missing route entries from the latest scan."""

    return list(_missing_routes)
