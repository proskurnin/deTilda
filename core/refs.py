"""Reference update utilities for project files.

Шаг 9 конвейера — самый важный для корректности результата.

Что делает update_all_refs_in_project для каждого файла:
  1. HTML: обновляет href/src/action по rename_map и маршрутам .htaccess
  2. HTML: комментирует теги <link rel="icon"> (иконки Tilda)
  3. HTML: заменяет ссылки на логотипы Tilda на 1px.png
  4. Все файлы: применяет rename_map (переименованные файлы)
  5. Все файлы: применяет replace_rules (til→ai, t-→ai-)
  6. JS: замены только внутри строковых литералов (безопасно для кода)

Возвращает (fixed_total, broken_total) — счётчики для отчёта.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from core import logger, utils
from core.config_loader import ConfigLoader
from core.htaccess import collect_routes

__all__ = ["update_all_refs_in_project"]


def _should_skip(url: str, ignore_prefixes: Iterable[str]) -> bool:
    return any(url.startswith(prefix) for prefix in ignore_prefixes)


def _is_internal_anchor(url: str) -> bool:
    """Return ``True`` when *url* points to an in-page anchor."""

    return url.startswith("#")


def _is_root_anchor(url: str) -> bool:
    """Return ``True`` when *url* points to a root-relative anchor."""

    return url.startswith("/#")


def _resolve_owner_page(path: Path, project_root: Path) -> str:
    """Return page filename that *path* belongs to for anchor resolution."""

    rel_path = path.relative_to(project_root).as_posix()
    if rel_path.startswith("files/"):
        name = path.name
        body_match = re.fullmatch(r"(page\d+)body\.html", name, re.IGNORECASE)
        if body_match:
            return f"{body_match.group(1)}.html"
    return path.name


def _is_same_page_root_anchor(
    url: str,
    *,
    current_path: Path,
    project_root: Path,
    routes: Dict[str, str],
) -> bool:
    """Check whether ``/#...`` anchor points to the current document."""

    if not _is_root_anchor(url):
        return False
    root_target = routes.get("/")
    if not root_target:
        return False
    owner_page = _resolve_owner_page(current_path, project_root)
    return owner_page == Path(root_target).name


def _replace_static_prefix(url: str) -> str:
    for prefix in ("css/", "js/", "images/", "files/"):
        if url.startswith("/" + prefix):
            return url[1:]
    return url


def _compile_replace_rules(rules: Iterable[object]) -> list[tuple[re.Pattern[str], str]]:
    """Компилирует ReplaceRule объекты в пары (pattern, replacement) для subn."""
    compiled: list[tuple[re.Pattern[str], str]] = []
    for rule in rules:
        if hasattr(rule, "pattern"):
            pattern = rule.pattern  # type: ignore[union-attr]
            replacement = str(getattr(rule, "replacement", ""))
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


_JS_STRING_RE = re.compile(r"""(?P<quote>["'])(?P<inner>(?:\\.|(?!\1).)*)(?P=quote)""", re.DOTALL)
_JS_REPLACE_HINT_RE = re.compile(
    r"""
    (?:
        \bt-[a-z0-9_-]+
        |data-tilda
        |tildamodal:
        |--t-[a-z0-9_-]+
        |\btilda-[a-z0-9_.-]+
        |\btild[a-z0-9_.-]*
        |\bwindow\.Tilda\b
        |\bTilda\b
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
_JS_WINDOW_TILDA_RE = re.compile(r"\bwindow\.Tilda\b")
_JS_TILDA_NAMESPACE_RE = re.compile(r"\bTilda(?=\.)")


def _apply_replace_rules_js(text: str, rules: Iterable[tuple[re.Pattern[str], str]]) -> tuple[str, int]:
    total = 0

    def _string_replacer(match: re.Match[str]) -> str:
        nonlocal total
        quote = match.group("quote")
        inner = match.group("inner")
        if not _JS_REPLACE_HINT_RE.search(inner):
            return match.group(0)
        updated, count = _apply_replace_rules(inner, rules)
        total += count
        return f"{quote}{updated}{quote}"

    text = _JS_STRING_RE.sub(_string_replacer, text)

    text, window_count = _JS_WINDOW_TILDA_RE.subn("window.aida", text)
    total += window_count
    text, namespace_count = _JS_TILDA_NAMESPACE_RE.subn("aida", text)
    total += namespace_count
    return text, total


def _apply_replace_rules_for_suffix(
    text: str,
    rules: Iterable[tuple[re.Pattern[str], str]],
    suffix: str,
) -> tuple[str, int]:
    """Применяет replace_rules с учётом типа файла.

    JS-файлы обрабатываются через _apply_replace_rules_js — замены только
    внутри строковых литералов, чтобы не сломать код.
    """
    if suffix == ".js":
        return _apply_replace_rules_js(text, rules)
    return _apply_replace_rules(text, rules)


def _apply_rename_map(text: str, rename_map: Dict[str, str]) -> tuple[str, int]:
    """Применяет карту переименований к тексту.

    Сортируем по длине убывающей — длинные совпадения имеют приоритет,
    чтобы избежать частичных замен (например page1.html раньше page1).
    """
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
    """Убирает служебные маркеры data-detilda-broken="1" из HTML.

    Маркеры добавляются в _update_links_in_html для битых ссылок —
    после обработки их нужно удалить из финального HTML.
    """
    text = re.sub(
        r'(<img\b[^>]*?)\s+alt="[^"]*"([^>]*?\sdata-detilda-broken="1")',
        lambda match: match.group(1) + match.group(2),
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r'\sdata-detilda-broken="1"', "", text, flags=re.IGNORECASE)
    return text


def _split_url(url: str) -> tuple[str, str]:
    """Разделяет URL на базовый путь и суффикс (query + fragment).

    Параметр ?t=... удаляется — Tilda использует его для cache-busting,
    он не несёт смысловой нагрузки и мешает сравнению ссылок.
    """
    split = urlsplit(url)
    base_url = urlunsplit((split.scheme, split.netloc, split.path, "", ""))

    suffix = ""

    if split.query:
        filtered_params = [
            (key, value)
            for key, value in parse_qsl(split.query, keep_blank_values=True)
            if key.lower() != "t"
        ]
        if filtered_params:
            suffix += "?" + urlencode(filtered_params, doseq=True)

    if split.fragment:
        suffix += f"#{split.fragment}"

    return base_url, suffix


def _update_links_in_html(
    text: str,
    routes: Dict[str, str],
    rename_map: Dict[str, str],
    project_root: Path,
    current_path: Path,
    ignore_prefixes: Iterable[str],
    link_rel_values: Iterable[str],
    replace_patterns: Iterable[str],
    comment_patterns: Iterable[str],
) -> tuple[str, int, int]:
    """Обновляет все ссылки в HTML-файле.

    Порядок обработки каждой ссылки:
      1. Внутренние якори (#) — пропускаем
      2. Ссылки на тот же корень (/#...) — упрощаем до якоря
      3. Внешние URL (http, //) — пропускаем
      4. Корневые пути (/) — ищем в маршрутах .htaccess, затем в rename_map
      5. Относительные пути — ищем в rename_map, проверяем существование
    Возвращает (новый текст, исправлено, битых).
    """
    fixed = 0
    broken = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal fixed, broken
        attr = match.group("attr")
        quote = match.group("quote") or '"'
        url = match.group("link")
        base_url, suffix = _split_url(url)

        if _is_internal_anchor(url):
            return match.group(0)
        if _is_same_page_root_anchor(
            url,
            current_path=current_path,
            project_root=project_root,
            routes=routes,
        ):
            fixed += 1
            return f"{attr}={quote}{suffix or '#'}{quote}"
        if _is_root_anchor(url):
            return match.group(0)

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
            last_segment = relative.rsplit("/", 1)[-1]
            if relative and "." not in last_segment:
                return match.group(0)
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

    # ВАЖНО: replace_patterns и comment_patterns обрабатываются ДО главного цикла,
    # чтобы заведомо известные мусорные ссылки (логотипы Tilda) были заменены
    # ДО того как broken-handler пометит их как битые (если файл уже удалён).

    # Заменяем ссылки на логотипы Tilda на прозрачный 1px.png
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

    # Комментируем ссылки на файлы Tilda (aidacopy.png и др.)
    def _comment_replacer(match: re.Match[str]) -> str:
        nonlocal fixed
        snippet = match.group(0)
        if "<!--" in snippet and "-->" in snippet:
            return snippet
        fixed += 1
        return f"<!-- {snippet} -->"

    for pattern_str in comment_patterns:
        try:
            comment_re = re.compile(pattern_str, re.IGNORECASE)
        except re.error:
            logger.warn(f"[refs] Некорректный паттерн комментирования: {pattern_str}")
            continue
        text = comment_re.sub(_comment_replacer, text)

    # Главный цикл: обновление и проверка ссылок (rename_map, маршруты, broken-handling)
    pattern = re.compile(
        r'(?P<attr>href|src|data-src|data-href|action)\s*=\s*(?P<quote>["\'])?(?P<link>[^"\'>]+)(?P=quote)',
        re.IGNORECASE,
    )
    text = pattern.sub(repl, text)

    # Комментируем <link rel="icon"> и <link rel="apple-touch-icon"> — иконки Tilda
    def _link_replacer(match: re.Match[str]) -> str:
        nonlocal fixed
        tag = match.group(1)
        if "<!--" in tag and "-->" in tag:
            return tag
        fixed += 1
        return f"<!-- {tag} -->"

    for rel_value in link_rel_values:
        link_pattern = re.compile(
            rf"(<link[^>]+rel=\"{re.escape(rel_value)}\"[^>]*>)",
            re.IGNORECASE,
        )
        text = link_pattern.sub(_link_replacer, text)

    text = _cleanup_broken_markup(text)
    return text, fixed, broken


def update_all_refs_in_project(
    project_root: Path,
    rename_map: Dict[str, str],
    loader: ConfigLoader | None = None,
    stats: Any | None = None,
) -> tuple[int, int]:
    """Обновляет все ссылки во всех текстовых файлах проекта.

    rename_map: карта переименований из assets.py {старый→новый}
    Возвращает (fixed_total, broken_total).
    """
    project_root = Path(project_root)
    rename_map = dict(rename_map)

    if loader is None:
        loader = ConfigLoader()

    patterns_cfg = loader.patterns()
    ignore_prefixes = tuple(patterns_cfg.ignore_prefixes)
    text_extensions = tuple(patterns_cfg.text_extensions) or (
        ".html", ".htm", ".css", ".js", ".php", ".txt",
    )
    replace_rules = _compile_replace_rules(patterns_cfg.replace_rules)

    images_cfg = loader.images()
    link_rel_values = images_cfg.comment_out_link_tags.rel_values
    replace_patterns = images_cfg.replace_links_with_1px.patterns
    comment_patterns = images_cfg.comment_out_links.patterns

    routes = collect_routes(project_root, loader, stats=stats)

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
                path,
                ignore_prefixes,
                link_rel_values,
                replace_patterns,
                comment_patterns,
            )

        text, rename_replacements = _apply_rename_map(text, rename_map)
        text, rule_replacements = _apply_replace_rules_for_suffix(text, replace_rules, suffix)

        # Сохраняем файл если содержимое изменилось — даже если изменения
        # связаны только с broken-маркерами (которые потом очищены).
        if text != original:
            utils.safe_write(path, text)
            logger.info(f"🔗 Обновлены ссылки: {utils.relpath(path, project_root)}")

        fixed_total += fixed + rename_replacements + rule_replacements
        broken_total += broken

    logger.info(
        f"✅ Исправлено ссылок: {fixed_total}, осталось битых: {broken_total}"
    )
    return fixed_total, broken_total
