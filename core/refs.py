"""Reference update utilities for HTML/CSS/JS files."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, Tuple

from core import logger, utils
from core.config_loader import ConfigLoader
from core.htaccess import collect_routes

__all__ = ["update_all_refs_in_project"]

def _should_skip(url: str, ignore_prefixes: Iterable[str]) -> bool:
    return any(url.startswith(prefix) for prefix in ignore_prefixes)


def _replace_static_prefix(url: str) -> str:
    for prefix in ("css/", "js/", "images/", "files/"):
        if url.startswith("/" + prefix):
            return url[1:]
    return url


def _update_links_in_html(
    text: str,
    routes: Dict[str, str],
    rename_map: Dict[str, str],
    project_root: Path,
    ignore_prefixes: Iterable[str],
    script_names: Iterable[str],
    link_rel_values: Iterable[str],
    replace_patterns: Iterable[str],
    comment_patterns: Iterable[str],
) -> Tuple[str, int, int]:
    fixed = 0
    broken = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal fixed, broken
        attr = match.group("attr")
        url = match.group("link")

        if _should_skip(url, ignore_prefixes) or url.startswith("../"):
            return match.group(0)

        if url.startswith("/"):
            if url in routes:
                new_url = routes[url]
                if new_url != url:
                    fixed += 1
                    return f'{attr}="{new_url}"'
            trimmed = _replace_static_prefix(url)
            if trimmed != url:
                fixed += 1
                return f'{attr}="{trimmed}"'
            relative = url.lstrip("/")
            if relative in rename_map:
                fixed += 1
                return f'{attr}="{rename_map[relative]}"'
            target = project_root / relative
            if not target.exists():
                broken += 1
            return match.group(0)

        if url in rename_map:
            fixed += 1
            return f'{attr}="{rename_map[url]}"'

        return match.group(0)

    pattern = re.compile(
        r'(?P<attr>href|src|data-src|data-href|action)\s*=\s*"(?P<link>[^"]+)"',
        re.IGNORECASE,
    )
    text = pattern.sub(repl, text)

    for script in script_names:
        script_pattern = re.compile(
            rf"(<script[^>]+{re.escape(script)}[^>]*></script>)",
            re.IGNORECASE,
        )
        text, count = script_pattern.subn(r"<!-- \1 -->", text)
        fixed += count

    for rel_value in link_rel_values:
        link_pattern = re.compile(
            rf"(<link[^>]+rel=\"{re.escape(rel_value)}\"[^>]*>)",
            re.IGNORECASE,
        )
        text, count = link_pattern.subn(r"<!-- \1 -->", text)
        fixed += count

    for pattern_str in replace_patterns:
        try:
            replace_re = re.compile(pattern_str, re.IGNORECASE)
        except re.error:
            logger.warn(f"[refs] Некорректный паттерн замены: {pattern_str}")
            continue
        text, count = replace_re.subn("images/1px.png", text)
        fixed += count

    for pattern_str in comment_patterns:
        try:
            comment_re = re.compile(pattern_str, re.IGNORECASE)
        except re.error:
            logger.warn(f"[refs] Некорректный паттерн комментирования: {pattern_str}")
            continue
        text, count = comment_re.subn(lambda m: f"<!-- {m.group(0)} -->", text)
        fixed += count

    return text, fixed, broken


def _apply_rename_map(text: str, rename_map: Dict[str, str]) -> tuple[str, int]:
    replacements = 0
    for old, new in rename_map.items():
        if old in text:
            text = text.replace(old, new)
            replacements += 1
    return text, replacements


def update_all_refs_in_project(
    project_root: Path,
    rename_map: Dict[str, str],
    loader: ConfigLoader,
) -> tuple[int, int]:
    project_root = Path(project_root)
    rename_map = dict(rename_map)

    patterns_cfg = loader.patterns()
    ignore_prefixes = tuple(patterns_cfg.get("ignore_prefixes", []))
    images_cfg = loader.images()
    service_cfg = loader.service_files()
    script_names = [
        value
        for value in service_cfg.get("scripts_to_comment_out_tags", {}).get("filenames", [])
        if isinstance(value, str)
    ]
    link_rel_values = [
        value
        for value in images_cfg.get("comment_out_link_tags", {}).get("rel_values", [])
        if isinstance(value, str)
    ]
    replace_patterns = [
        value
        for value in images_cfg.get("replace_links_with_1px", {}).get("patterns", [])
        if isinstance(value, str)
    ]
    comment_patterns = [
        value
        for value in images_cfg.get("comment_out_links", {}).get("patterns", [])
        if isinstance(value, str)
    ]

    routes = collect_routes(project_root, loader)

    fixed_total = 0
    broken_total = 0

    for path in project_root.rglob("*.html"):
        try:
            text = utils.safe_read(path)
        except Exception as exc:
            logger.warn(f"[refs] Пропуск {path.name}: {exc}")
            continue
        original = text
        text, fixed, broken = _update_links_in_html(
            text,
            routes,
            rename_map,
            project_root,
            ignore_prefixes,
            script_names,
            link_rel_values,
            replace_patterns,
            comment_patterns,
        )
        fixed_total += fixed
        broken_total += broken
        text, replacements = _apply_rename_map(text, rename_map)
        fixed_total += replacements
        if text != original:
            utils.safe_write(path, text)
            logger.info(f"🔗 Обновлены ссылки: {utils.relpath(path, project_root)}")

    for ext in (".css", ".js"):
        for path in project_root.rglob(f"*{ext}"):
            try:
                text = utils.safe_read(path)
            except Exception:
                continue
            original = text
            text, replacements = _apply_rename_map(text, rename_map)
            if replacements:
                fixed_total += replacements
                utils.safe_write(path, text)
                logger.info(f"🔗 Обновлены ссылки: {utils.relpath(path, project_root)}")

    logger.info(f"✅ Исправлено ссылок: {fixed_total}, осталось битых: {broken_total}")
    return fixed_total, broken_total
