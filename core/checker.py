"""Lightweight link checker for deTilda."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from core import logger, utils
from core.config_loader import ConfigLoader
from core.downloader import download_to_project
from core.htaccess import collect_routes, get_route_info

__all__ = ["FormIntegrationResult", "LinkCheckerResult", "TildaRemnantsResult", "check_forms_integration", "check_links", "check_tilda_remnants"]


@dataclass
class LinkCheckerResult:
    checked: int = 0
    broken: int = 0


@dataclass
class TildaRemnantsResult:
    files_with_remnants: int = 0
    total_occurrences: int = 0


@dataclass
class FormIntegrationResult:
    forms_found: int = 0
    forms_hooked: int = 0
    warnings: int = 0


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


def _is_absolute_url(link: str) -> bool:
    return link.startswith(("http://", "https://", "//"))


def _apply_replace_rules(link: str, rules: list[dict]) -> str:
    result = link
    for rule in rules:
        pattern = rule.get("pattern")
        replacement = rule.get("replacement", "")
        if not pattern:
            continue
        try:
            result = re.sub(str(pattern), str(replacement), result)
        except re.error:
            pass
    return result


def check_tilda_remnants(project_root: Path, loader: ConfigLoader) -> TildaRemnantsResult:
    """Find and fix any links still containing 'tilda' after the pipeline.

    - Absolute URLs (http/https//) → download locally, replace with relative path
    - Local paths → apply replace_rules from config (til→ai)

    Goal: zero tilda references in the final output.
    """

    project_root = Path(project_root)
    patterns_cfg = loader.patterns()
    service_cfg = loader.service_files()
    link_patterns = patterns_cfg.get("links", [])
    replace_rules = patterns_cfg.get("replace_rules", [])
    download_rules = service_cfg.get("remote_assets", {}).get("rules", [])
    text_extensions = tuple(patterns_cfg.get("text_extensions", [".html", ".htm", ".css", ".js"]))

    result = TildaRemnantsResult()

    for file_path in utils.list_files_recursive(project_root, extensions=text_extensions):
        try:
            text = utils.safe_read(file_path)
        except Exception:
            continue

        original = text
        file_hits = 0

        for link in _iter_links(original, link_patterns):
            if "tilda" not in link.lower():
                continue

            if _is_absolute_url(link):
                # Скачиваем локально и заменяем URL на относительный путь
                downloaded = download_to_project(link, project_root, download_rules)
                if downloaded:
                    dest_path, _ = downloaded
                    rel = os.path.relpath(dest_path, file_path.parent).replace("\\", "/")
                    text = text.replace(link, rel)
                    logger.info(
                        f"[tilda-remnants] Локализован: {link} → {rel} "
                        f"в {utils.relpath(file_path, project_root)}"
                    )
                else:
                    # Не удалось скачать — применяем replace_rules
                    fixed = _apply_replace_rules(link, replace_rules)
                    if fixed != link:
                        text = text.replace(link, fixed)
                        logger.warn(
                            f"[tilda-remnants] Не скачан, применены правила замены: "
                            f"{link} → {fixed} в {utils.relpath(file_path, project_root)}"
                        )
                    else:
                        file_hits += 1
                        logger.warn(
                            f"[tilda-remnants] Не удалось исправить: {link} "
                            f"в {utils.relpath(file_path, project_root)}"
                        )
            else:
                # Локальный путь — применяем replace_rules
                fixed = _apply_replace_rules(link, replace_rules)
                if fixed != link:
                    text = text.replace(link, fixed)
                    logger.info(
                        f"[tilda-remnants] Исправлен локальный путь: {link} → {fixed} "
                        f"в {utils.relpath(file_path, project_root)}"
                    )
                else:
                    file_hits += 1
                    logger.warn(
                        f"[tilda-remnants] Не удалось исправить: {link} "
                        f"в {utils.relpath(file_path, project_root)}"
                    )

        if text != original:
            utils.safe_write(file_path, text)

        if file_hits:
            result.files_with_remnants += 1
            result.total_occurrences += file_hits

    if result.total_occurrences:
        logger.warn(
            f"[tilda-remnants] ❌ Осталось неисправленных: {result.total_occurrences} "
            f"в {result.files_with_remnants} файлах — требуется ручная проверка"
        )
    else:
        logger.info("[tilda-remnants] ✓ Ссылок с 'tilda' не найдено")

    return result


def check_forms_integration(project_root: Path) -> FormIntegrationResult:
    """Verify that every HTML form has the form handler script on the same page."""

    project_root = Path(project_root)
    html_files = list(project_root.rglob("*.html"))
    files_dir = project_root / "files"
    body_files = list(files_dir.glob("*body.html")) if files_dir.exists() else []

    forms_found = 0
    forms_hooked = 0
    form_pattern = re.compile(r"<form\b", re.IGNORECASE)
    handler_pattern = re.compile(r"form-handler\.js", re.IGNORECASE)

    for file_path in html_files + body_files:
        try:
            content = utils.safe_read(file_path)
        except Exception:
            continue

        file_forms = len(form_pattern.findall(content))
        if file_forms == 0:
            continue
        forms_found += file_forms
        if handler_pattern.search(content):
            forms_hooked += file_forms

    result = FormIntegrationResult(forms_found=forms_found, forms_hooked=forms_hooked)
    if forms_found != forms_hooked:
        result.warnings = 1
        logger.warn(
            f"[forms-check] Найдено форм: {forms_found}, подключено к handler: {forms_hooked}"
        )
    else:
        logger.info(f"[forms-check] Формы проверены: {forms_found}, все подключены корректно")
    return result
