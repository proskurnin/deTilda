"""Link and form integrity checks for the deTilda pipeline.

Три проверки выполняются в конце конвейера (шаги 12–14):

  check_links (шаг 14):
    Финальная проверка всех внутренних ссылок в HTML-файлах.
    Цель: 0 битых ссылок. Логирует каждую битую ссылку как предупреждение.

  check_tilda_remnants (шаг 13):
    Находит и исправляет оставшиеся ссылки со словом 'tilda':
    - Абсолютные URL → скачивает локально, заменяет на относительный путь
    - Локальные пути → применяет replace_rules (til→ai)
    Цель: 0 остатков. Неисправленные попадают в финальный отчёт.

  check_forms_integration (шаг 12):
    Статическая проверка: у каждой HTML-страницы с формой подключён
    form-handler.js. Реальная отправка не тестируется — только наличие скрипта.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from core import logger, utils
from core.config_loader import ConfigLoader
from core.downloader import download_to_project
from core.htaccess import HtaccessResult, collect_routes

__all__ = [
    "FormIntegrationResult",
    "LinkCheckerResult",
    "TildaRemnantsResult",
    "check_forms_integration",
    "check_links",
    "check_tilda_remnants",
]


@dataclass
class LinkCheckerResult:
    checked: int = 0
    broken: int = 0
    htaccess_result: HtaccessResult | None = None


@dataclass
class TildaRemnantsResult:
    files_with_remnants: int = 0
    total_occurrences: int = 0  # ссылки которые не удалось исправить
    tilda_filenames: list[str] = field(default_factory=list)  # файлы с 'tilda' в имени


@dataclass
class FormIntegrationResult:
    forms_found: int = 0
    forms_hooked: int = 0
    warnings: int = 0  # 1 если есть непривязанные формы, иначе 0


def _compile_link_patterns(patterns: Iterable[str]) -> list[re.Pattern[str]]:
    """Компилирует паттерны из config.yaml для повторного использования."""
    result = []
    for pattern in patterns:
        try:
            result.append(re.compile(pattern))
        except re.error:
            logger.warn(f"[checker] Некорректный паттерн: {pattern}")
    return result


def _iter_links(text: str, compiled: Iterable[re.Pattern[str]]) -> Iterable[str]:
    """Извлекает ссылки из текста по скомпилированным паттернам."""
    for regex in compiled:
        for match in regex.finditer(text):
            link = match.groupdict().get("link")
            if link:
                yield link


def _strip_cache_busting_param(link: str) -> str:
    """Удаляет ?t=... (cache-busting параметр Tilda) и fragment из URL."""
    split = urlsplit(link)
    filtered_params = [
        (key, value)
        for key, value in parse_qsl(split.query, keep_blank_values=True)
        if key.lower() != "t"
    ]
    sanitized_query = urlencode(filtered_params, doseq=True)
    return urlunsplit((split.scheme, split.netloc, split.path, sanitized_query, ""))


def _get_effective_base_directory(file_path: Path, project_root: Path) -> Path:
    """Возвращает базовую директорию для разрешения относительных ссылок.

    Tilda хранит body-файлы в files/page123body.html — относительные ссылки
    в них разрешаются относительно page123.html (родительского файла), а не
    относительно files/. Эта функция находит правильную базовую директорию.
    """
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


def _relative_candidates(
    file_path: Path,
    base_directory: Path,
    link_target: str,
) -> list[Path]:
    """Return possible filesystem targets for a relative link.

    Body fragments can be interpreted in two contexts:
    - as injected HTML inside the real page, where links resolve from page root;
    - as physical files under files/, where links like ../page.html are valid.
    """
    candidates = [(base_directory / link_target).resolve()]
    physical_candidate = (file_path.parent / link_target).resolve()
    if physical_candidate not in candidates:
        candidates.append(physical_candidate)
    return candidates


def check_links(project_root: Path, loader: ConfigLoader) -> LinkCheckerResult:
    """Проверяет все внутренние ссылки в HTML-файлах проекта.

    Внешние URL (http://, https://, //) и якори (#) игнорируются.
    Каждая битая ссылка логируется как предупреждение.
    """
    project_root = Path(project_root)
    patterns_cfg = loader.patterns()
    ignore_prefixes = tuple(patterns_cfg.ignore_prefixes)
    compiled_link_patterns = _compile_link_patterns(patterns_cfg.links)

    htaccess_result = collect_routes(project_root, loader)
    result = LinkCheckerResult(htaccess_result=htaccess_result)

    for file_path in utils.list_files_recursive(project_root, extensions=(".html", ".htm")):
        try:
            text = utils.safe_read(file_path)
        except Exception:
            continue
        base_directory = _get_effective_base_directory(file_path, project_root)

        for link in _iter_links(text, compiled_link_patterns):
            normalized_link = _strip_cache_busting_param(link)
            if not normalized_link:
                continue

            link_parts = urlsplit(normalized_link)
            link_path = link_parts.path

            if any(normalized_link.startswith(prefix) for prefix in ignore_prefixes):
                continue

            if link.startswith("/"):
                route_info = htaccess_result.get_route_info(link_path or normalized_link)
                if route_info and route_info.exists and route_info.path is not None:
                    candidate = route_info.path
                else:
                    candidate = project_root / (link_path or normalized_link).lstrip("/")
                candidates = [candidate]
            else:
                candidates = _relative_candidates(
                    file_path,
                    base_directory,
                    link_path or normalized_link,
                )

            result.checked += 1
            if not any(candidate.exists() for candidate in candidates):
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


def _apply_replace_rules(link: str, rules: list) -> str:
    """Применяет replace_rules к ссылке (ReplaceRule объекты из config.yaml)."""
    result = link
    for rule in rules:
        try:
            if hasattr(rule, "pattern") and rule.pattern:
                result = re.sub(str(rule.pattern), str(getattr(rule, "replacement", "")), result)
        except re.error:
            pass
    return result


def check_tilda_remnants(project_root: Path, loader: ConfigLoader) -> TildaRemnantsResult:
    """Находит и исправляет оставшиеся ссылки со словом 'tilda'.

    Абсолютные URL → скачивает локально, заменяет на относительный путь.
    Локальные пути → применяет replace_rules (til→ai).
    Неисправленные — логируются, попадают в total_occurrences.
    Цель: 0.
    """
    project_root = Path(project_root)
    patterns_cfg = loader.patterns()
    service_cfg = loader.service_files()
    compiled_link_patterns = _compile_link_patterns(patterns_cfg.links)
    replace_rules = patterns_cfg.replace_rules
    download_rules = [
        {"folder": r.folder, "extensions": list(r.extensions)}
        for r in service_cfg.remote_assets.rules
    ]
    text_extensions = tuple(patterns_cfg.text_extensions) or (".html", ".htm", ".css", ".js")

    result = TildaRemnantsResult()

    for file_path in utils.list_files_recursive(project_root, extensions=text_extensions):
        try:
            text = utils.safe_read(file_path)
        except Exception:
            continue

        original = text
        file_hits = 0

        for link in _iter_links(original, compiled_link_patterns):
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

    # Сканируем имена файлов — assets мог пропустить файлы с 'tilda' в имени
    for file_path in sorted(project_root.rglob("*")):
        if file_path.is_file() and "tilda" in file_path.name.lower():
            rel = utils.relpath(file_path, project_root)
            result.tilda_filenames.append(rel)
            logger.warn(f"[tilda-remnants] Файл с именем tilda: {rel}")

    if result.total_occurrences:
        logger.warn(
            f"[tilda-remnants] ❌ Осталось неисправленных ссылок: {result.total_occurrences} "
            f"в {result.files_with_remnants} файлах — требуется ручная проверка"
        )
    else:
        logger.info("[tilda-remnants] ✓ Ссылок с 'tilda' не найдено")

    if result.tilda_filenames:
        logger.warn(
            f"[tilda-remnants] ❌ Файлов с именем tilda: {len(result.tilda_filenames)} "
            "— требуется ручная проверка"
        )
    else:
        logger.info("[tilda-remnants] ✓ Файлов с именем tilda не найдено")

    return result


def check_forms_integration(project_root: Path) -> FormIntegrationResult:
    """Проверяет что каждая HTML-страница с формой имеет подключённый form-handler.js.

    Проверка статическая — анализирует HTML, не отправляет реальные запросы.
    warnings=1 если хотя бы одна форма не подключена к handler.
    """
    project_root = Path(project_root)
    form_pattern = re.compile(r"<form\b", re.IGNORECASE)
    handler_pattern = re.compile(r"form-handler\.js", re.IGNORECASE)

    forms_found = 0
    forms_hooked = 0

    for file_path in utils.list_files_recursive(project_root, extensions=(".html", ".htm")):
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
