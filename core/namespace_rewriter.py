"""Final Aida namespace rewrite for processed projects.

This step runs after external/runtime assets have been downloaded. It rewrites
the runtime namespace consistently across HTML, CSS, JS and file paths so DOM
classes, data attributes, selectors and function calls move together.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from core import logger, utils
from core.refs import _walk_js_strings

__all__ = [
    "NamespaceRewriteResult",
    "rewrite_project_namespace",
    "rewrite_text",
    "scan_leftovers",
]


TEXT_EXTENSIONS = (".html", ".htm", ".css", ".js", ".json", ".svg", ".php", ".txt")

_WORD_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bTILDA"), "AIDA"),
    (re.compile(r"\bTilda"), "Aida"),
    (re.compile(r"\btilda"), "aida"),
    (re.compile(r"\bTILD"), "AID"),
    (re.compile(r"\bTild"), "Aid"),
    (re.compile(r"\btild"), "aid"),
    (re.compile(r"\bTIL(?!eColor\b|eImage\b)"), "AI"),
    (re.compile(r"\bTil(?!eColor\b|eImage\b)"), "Ai"),
    (re.compile(r"\btil(?!eColor\b|eImage\b)"), "ai"),
)

_CLASS_PREFIX_RE = re.compile(r"\bt-")
_FUNCTION_IDENTIFIER_RE = re.compile(r"\bt(?=(?:\d+_|_))[A-Za-z0-9_$]*")

_CRITICAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("data-tilda-", re.compile(r"data-tilda-", re.IGNORECASE)),
    ("data-tild-", re.compile(r"data-tild-", re.IGNORECASE)),
    ("data-til-", re.compile(r"data-til-", re.IGNORECASE)),
    ("class contains t-", re.compile(r"\bclass\s*=\s*(['\"])[^'\"]*\bt-", re.IGNORECASE)),
    (".t- selector", re.compile(r"(?<![A-Za-z0-9_-])\.t-", re.IGNORECASE)),
    ("t_onReady", re.compile(r"\bt_onReady\b")),
    ("t_onFuncLoad", re.compile(r"\bt_onFuncLoad\b")),
    ("t396_init", re.compile(r"\bt396_init\b")),
    ("t_zeroForms__init", re.compile(r"\bt_zeroForms__init\b")),
    ("t_* runtime function", re.compile(r"\bt(?=(?:\d+_|_))[A-Za-z0-9_$]*\b")),
)

_WARNING_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("external tilda URL", re.compile(r"(?:https?:)?//[^\s'\"<>]*tilda[^\s'\"<>]*", re.IGNORECASE)),
)


@dataclass
class NamespaceRewriteResult:
    files_checked: int = 0
    files_updated: int = 0
    replacements: int = 0
    renamed_paths: int = 0
    critical_leftovers: dict[str, int] = field(default_factory=dict)
    warning_leftovers: dict[str, int] = field(default_factory=dict)
    report_path: Path | None = None

    @property
    def critical_leftovers_total(self) -> int:
        return sum(self.critical_leftovers.values())

    @property
    def warning_leftovers_total(self) -> int:
        return sum(self.warning_leftovers.values())


def _apply_word_replacements(text: str) -> tuple[str, int]:
    total = 0
    for pattern, replacement in _WORD_REPLACEMENTS:
        text, count = pattern.subn(replacement, text)
        total += count
    return text, total


def _apply_class_prefix_replacements(text: str) -> tuple[str, int]:
    text, count = _CLASS_PREFIX_RE.subn("ai-", text)
    return text, count


def _apply_function_replacements(text: str) -> tuple[str, int]:
    def _replace(match: re.Match[str]) -> str:
        token = match.group(0)
        return "ai" + token[1:]

    return _FUNCTION_IDENTIFIER_RE.subn(_replace, text)


def _rewrite_string_content(text: str) -> tuple[str, int]:
    if text.lstrip().lower().startswith("data:"):
        return text, 0
    total = 0
    text, count = _apply_word_replacements(text)
    total += count
    text, count = _apply_class_prefix_replacements(text)
    total += count
    text, count = _apply_function_replacements(text)
    total += count
    return text, total


def _rewrite_js_text(text: str) -> tuple[str, int]:
    total = 0
    spans = _walk_js_strings(text)
    pieces: list[str] = []
    cursor = 0
    for start, end in spans:
        pieces.append(text[cursor:start])
        quote = text[start]
        inner = text[start + 1 : end - 1]
        updated, count = _rewrite_string_content(inner)
        total += count
        pieces.append(quote + updated + quote)
        cursor = end
    pieces.append(text[cursor:])
    text = "".join(pieces)

    text, count = _apply_function_replacements(text)
    total += count
    text, count = re.subn(r"\bwindow\.Tilda\b", "window.Aida", text)
    total += count
    text, count = re.subn(r"\bTilda(?=\.)", "Aida", text)
    total += count
    return text, total


def rewrite_text(text: str, suffix: str) -> tuple[str, int]:
    """Rewrite namespace-sensitive tokens for one file body."""
    suffix = suffix.lower()
    if suffix == ".js":
        return _rewrite_js_text(text)

    total = 0
    text, count = _apply_word_replacements(text)
    total += count
    text, count = _apply_class_prefix_replacements(text)
    total += count
    text, count = _apply_function_replacements(text)
    total += count
    return text, total


def _rewrite_path_name(name: str) -> str:
    rewritten, _count = _apply_word_replacements(name)
    return rewritten


def _rename_namespace_paths(project_root: Path) -> tuple[dict[str, str], int]:
    rename_map: dict[str, str] = {}
    renamed = 0

    paths = sorted(
        [path for path in project_root.rglob("*") if path != project_root],
        key=lambda item: len(item.parts),
        reverse=True,
    )
    for path in paths:
        if not path.exists():
            continue
        new_name = _rewrite_path_name(path.name)
        if new_name == path.name:
            continue
        destination = path.with_name(new_name)
        old_rel = utils.relpath(path, project_root)
        if destination.exists():
            logger.warn(
                f"[namespace_rewrite] Пропуск переименования из-за конфликта: {old_rel}"
            )
            continue
        try:
            path.rename(destination)
        except OSError as exc:
            logger.warn(f"[namespace_rewrite] Не удалось переименовать {old_rel}: {exc}")
            continue

        new_rel = utils.relpath(destination, project_root)
        rename_map[old_rel] = new_rel
        rename_map[path.name] = destination.name
        renamed += 1
        logger.info(f"[namespace_rewrite] Переименован: {old_rel} → {new_rel}")

    return rename_map, renamed


def _apply_rename_map(text: str, rename_map: dict[str, str]) -> tuple[str, int]:
    total = 0
    for old, new in sorted(rename_map.items(), key=lambda item: len(item[0]), reverse=True):
        if not old or old == new:
            continue
        text, count = re.subn(re.escape(old), new, text)
        total += count
    return text, total


def scan_leftovers(project_root: Path) -> tuple[dict[str, int], dict[str, int]]:
    critical: dict[str, int] = {}
    warnings: dict[str, int] = {}
    for path in utils.list_files_recursive(project_root, extensions=TEXT_EXTENSIONS):
        try:
            text = utils.safe_read(path)
        except Exception:
            continue
        for label, pattern in _CRITICAL_PATTERNS:
            count = len(pattern.findall(text))
            if count:
                critical[label] = critical.get(label, 0) + count
        for label, pattern in _WARNING_PATTERNS:
            count = len(pattern.findall(text))
            if count:
                warnings[label] = warnings.get(label, 0) + count

    for path in project_root.rglob("*"):
        if not path.exists():
            continue
        name = path.name
        if re.search(r"\btilda", name, re.IGNORECASE):
            critical["filename tilda"] = critical.get("filename tilda", 0) + 1
        elif re.search(r"\btild", name, re.IGNORECASE):
            critical["filename tild"] = critical.get("filename tild", 0) + 1
        elif re.search(r"\btil", name, re.IGNORECASE):
            critical["filename til"] = critical.get("filename til", 0) + 1

    return critical, warnings


def _write_report(project_root: Path, result: NamespaceRewriteResult) -> Path | None:
    project_name = logger.get_project_name()
    if not project_name:
        return None
    logs_dir = logger.get_logs_dir()
    report_path = logs_dir / f"{project_name}_namespace_rewrite_report.txt"
    lines = [
        "Namespace rewrite report",
        f"Project: {project_root.name}",
        f"Files checked: {result.files_checked}",
        f"Files updated: {result.files_updated}",
        f"Text replacements: {result.replacements}",
        f"Renamed paths: {result.renamed_paths}",
        "Critical leftovers:",
    ]
    if result.critical_leftovers:
        for label, count in sorted(result.critical_leftovers.items()):
            lines.append(f"  {count} x {label}")
    else:
        lines.append("  0")
    lines.append("Warnings:")
    if result.warning_leftovers:
        for label, count in sorted(result.warning_leftovers.items()):
            lines.append(f"  {count} x {label}")
    else:
        lines.append("  0")

    try:
        utils.safe_write(report_path, "\n".join(lines) + "\n")
        return report_path
    except Exception as exc:
        logger.warn(f"[namespace_rewrite] Не удалось сохранить отчёт: {exc}")
        return None


def rewrite_project_namespace(project_root: Path) -> NamespaceRewriteResult:
    """Rewrite filenames and text content to the final Aida namespace."""
    project_root = Path(project_root)
    result = NamespaceRewriteResult()
    rename_map, renamed_paths = _rename_namespace_paths(project_root)
    result.renamed_paths = renamed_paths

    for path in utils.list_files_recursive(project_root, extensions=TEXT_EXTENSIONS):
        result.files_checked += 1
        try:
            original = utils.safe_read(path)
        except Exception as exc:
            logger.warn(f"[namespace_rewrite] Пропуск {path.name}: {exc}")
            continue

        text = original
        replacements = 0
        text, count = _apply_rename_map(text, rename_map)
        replacements += count
        text, count = rewrite_text(text, path.suffix)
        replacements += count

        if text != original:
            utils.safe_write(path, text)
            result.files_updated += 1
            result.replacements += replacements
            logger.info(
                "[namespace_rewrite] Обновлён namespace: "
                f"{utils.relpath(path, project_root)} ({replacements})"
            )

    critical, warnings = scan_leftovers(project_root)
    result.critical_leftovers = critical
    result.warning_leftovers = warnings
    result.report_path = _write_report(project_root, result)

    if result.critical_leftovers:
        logger.warn(
            "[namespace_rewrite] Остались критичные namespace-паттерны: "
            + ", ".join(
                f"{label}={count}" for label, count in sorted(result.critical_leftovers.items())
            )
        )
    else:
        logger.info("[namespace_rewrite] Критичных остатков старого namespace не найдено")

    if result.report_path:
        logger.ok(
            "[namespace_rewrite] Отчёт сохранён: "
            f"{utils.relpath(result.report_path, logger.get_logs_dir())}"
        )
    return result
