"""Helpers for reading Apache ``.htaccess`` routing rules."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict

from core import logger, utils
from core.config_loader import ConfigLoader

__all__ = ["collect_routes"]


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


def collect_routes(project_root: Path, loader: ConfigLoader) -> Dict[str, str]:
    routes: Dict[str, str] = {}
    rewrite_re, redirect_re = _load_patterns(loader)

    for file_path in _iter_htaccess_files(project_root):
        try:
            text = utils.safe_read(file_path)
        except Exception as exc:
            logger.warn(f"[htaccess] Не удалось прочитать {file_path}: {exc}")
            continue

        for match in rewrite_re.finditer(text):
            alias, target = match.groups()
            alias = "/" + alias.strip("/")
            routes[alias] = target.strip()
            logger.debug(f"[htaccess] {alias} → {target.strip()}")

        for match in redirect_re.finditer(text):
            alias, target = match.groups()
            routes[alias.strip()] = target.strip()
            logger.debug(f"[htaccess] redirect {alias.strip()} → {target.strip()}")

        index_match = re.search(r"DirectoryIndex\s+([^\s]+\.html)", text, re.IGNORECASE)
        if index_match:
            routes["/"] = index_match.group(1).strip()
            logger.debug(f"[htaccess] / → {routes['/']} (DirectoryIndex)")

    if routes:
        logger.info(f"🔗 Обнаружено маршрутов из htaccess: {len(routes)}")
    else:
        logger.warn("⚠️ В htaccess не найдено RewriteRule.")
    return routes
