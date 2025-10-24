"""Reference update utilities for project files."""
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


def _compile_replace_rules(rules: Iterable[object]) -> list[tuple[re.Pattern[str], str]]:
    compiled: list[tuple[re.Pattern[str], str]] = []
    for rule in rules:
        if isinstance(rule, dict):
            pattern = rule.get("pattern")
            replacement = str(rule.get("replacement", ""))
        elif isinstance(rule, str):
            pattern = rule
            replacement = ""
        else:
            continue
        if not isinstance(pattern, str):
            continue
        try:
            compiled.append((re.compile(pattern, re.IGNORECASE), replacement))
        except re.error:
            logger.warn(f"[refs] Некорректное правило замены: {pattern}")
    return compiled


def _apply_replace_rules(text: str, rules: Iterable[tuple[re.Pattern[str], str]]) -> tuple[str, int]:
    total = 0
    for pattern, replacement in rules:
        text, count = pattern.subn(replacement, text)
        total += count
    return text, total

def _apply_rename_map(text: str, rename_map: Dict[str, str]) -> tuple[str, int]:
    replacements = 0
    for old, new in sorted(rename_map.items(), key=lambda item: len(item[0]), reverse=True):
        if not old:
            continue
        escaped = re.escape(old)
        pattern = re.compile(escaped)
        text, count = pattern.subn(new, text)
        replacements += count
    return text, replacements


def _cleanup_broken_markup(text: str) -> str:
    text = re.sub(
        r'(<img\\b[^>]*?)\\s+alt="[^"]*"([^>]*?\\sdata-detilda-broken="1")',
        lambda match: match.group(1) + match.group(2),
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\\sdata-detilda-broken=\"1\"", "", text, flags=re.IGNORECASE)
    return text


def _split_url(url: str) -> tuple[str, str]:
    for delimiter in ("?", "#"):
        if delimiter in url:
            index = url.index(delimiter)
            return url[:index], url[index:]
    return url, ""


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
        quote = match.group("quote") or '"'
        url = match.group("link")
        base_url, suffix = _split_url(url)

        if _should_skip(url, ignore_prefixes) or base_url.startswith("../"):
            return match.group(0)

        if base_url.startswith("/"):
            route_key = base_url
            if route_key in routes:
                new_url = routes[route_key]
                if new_url != route_key:
                    fixed += 1
                    return f"{attr}={quote}{new_url}{suffix}{quote}"
            trimmed = _replace_static_prefix(base_url)
            if trimmed != base_url:
                fixed += 1
                return f"{attr}={quote}{trimmed}{suffix}{quote}"
            relative = base_url.lstrip("/")
            if relative in rename_map:
                fixed += 1
                return f"{attr}={quote}{rename_map[relative]}{suffix}{quote}"
            target = project_root / relative
            if not target.exists():
                broken += 1
                return f"{attr}={quote}#{quote} data-detilda-broken=\"1\""
            return match.group(0)

        if base_url in rename_map:
            fixed += 1
            return f"{attr}={quote}{rename_map[base_url]}{suffix}{quote}"

        if base_url and not (
            base_url.startswith("http://")
            or base_url.startswith("https://")
            or base_url.startswith("//")
        ):
            candidate = (project_root / base_url).resolve()
            if not candidate.exists():
                broken += 1
                return f"{attr}={quote}#{quote} data-detilda-broken=\"1\""

        return match.group(0)

    pattern = re.compile(
        r'(?P<attr>href|src|data-src|data-href|action)\\s*=\\s*(?P<quote>["\'])?(?P<link>[^"\'>]+)(?P=quote)',
        re.IGNORECASE,
    )
    text = pattern.sub(repl, text)

    for script in script_names:
        script_pattern = re.compile(
            rf"(<script[^>]+{re.escape(script)}[^>]*></script>)",
            re.IGNORECASE,
        )

        def _script_replacer(match: re.Match[str]) -> str:
            nonlocal fixed
            tag = match.group(1)
            if "<!--" in tag and "-->" in tag:
                return tag
            fixed += 1
            return f"<!-- {tag} -->"

        text = script_pattern.sub(_script_replacer, text)

    for rel_value in link_rel_values:
        link_pattern = re.compile(
            rf"(<link[^>]+rel=\"{re.escape(rel_value)}\"[^>]*>)",
            re.IGNORECASE,
        )

        def _link_replacer(match: re.Match[str]) -> str:
            nonlocal fixed
            tag = match.group(1)
            if "<!--" in tag and "-->" in tag:
                return tag
            fixed += 1
            return f"<!-- {tag} -->"

        text = link_pattern.sub(_link_replacer, text)

    for pattern_str in replace_patterns:
        try:
            replace_re = re.compile(pattern_str, re.IGNORECASE)
        except re.error:
            logger.warn(f"[refs] Некорректный паттерн замены: {pattern_str}")
            continue
        new_text, count = replace_re.subn("images/1px.png", text)
        if count:
            fixed += count
            text = new_text

    for pattern_str in comment_patterns:
        try:
            comment_re = re.compile(pattern_str, re.IGNORECASE)
        except re.error:
            logger.warn(f"[refs] Некорректный паттерн комментирования: {pattern_str}")
            continue

        def _comment_replacer(match: re.Match[str]) -> str:
            nonlocal fixed
            snippet = match.group(0)
            if "<!--" in snippet and "-->" in snippet:
                return snippet
            fixed += 1
            return f"<!-- {snippet} -->"

        text = comment_re.sub(_comment_replacer, text)

    text = _cleanup_broken_markup(text)
    return text, fixed, broken

def update_all_refs_in_project(
    project_root: Path,
    rename_map: Dict[str, str],
    loader: ConfigLoader,
) -> tuple[int, int]:
    project_root = Path(project_root)
    rename_map = dict(rename_map)

    patterns_cfg = loader.patterns()
    ignore_prefixes = tuple(patterns_cfg.get("ignore_prefixes", []))
    text_extensions = tuple(patterns_cfg.get("text_extensions", [])) or (
        ".html",
        ".htm",
        ".css",
        ".js",
        ".php",
        ".txt",
    )
    replace_rules = _compile_replace_rules(patterns_cfg.get("replace_rules", []))

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

    html_extensions = {".html", ".htm"}
    for path in utils.list_files_recursive(project_root, extensions=text_extensions):
        suffix = path.suffix.lower()
        try:
            text = utils.safe_read(path)
        except Exception as exc:
            logger.warn(f"[refs] Пропуск {path.name}: {exc}")
            continue

        original = text
        fixed = 0
        broken = 0

        if suffix in html_extensions:
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

        text, rename_replacements = _apply_rename_map(text, rename_map)
        text, rule_replacements = _apply_replace_rules(text, replace_rules)

        total_changes = fixed + rename_replacements + rule_replacements
        if total_changes and text != original:
            utils.safe_write(path, text)
            logger.info(f"🔗 Обновлены ссылки: {utils.relpath(path, project_root)}")

        fixed_total += fixed + rename_replacements + rule_replacements
        broken_total += broken

    logger.info(
        f"✅ Исправлено ссылок: {fixed_total}, осталось битых: {broken_total}"
    )
    return fixed_total, broken_total
