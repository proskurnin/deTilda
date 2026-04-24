"""Text cleanup helpers for the deTilda pipeline.

Шаг 3 конвейера. Удаляет служебные строки и ссылки Tilda из текстовых файлов.

Обрабатывает только файлы из списка cleaner_options.files_to_clean_tilda_refs:
  - robots.txt: удаляет строки Disallow с путями Tilda (формы, трекинг, корзина)
  - readme.txt: удаляет упоминания Tilda, заменяет "tilda" → "site"
  - оба файла: удаляет остаточные ссылки на домены Tilda (tilda.ws, tildacdn.com)

HTML-файлы на этом шаге НЕ трогаются — для них есть refs.py и script_cleaner.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from core import logger, utils
from core.config_loader import ConfigLoader
from core.project import ProjectContext

__all__ = ["CleanStats", "clean_project_files", "clean_text_files"]


@dataclass
class CleanStats:
    updated: int = 0  # количество изменённых файлов
    removed: int = 0  # зарезервировано (сейчас не используется)


def _compile_patterns(patterns: Iterable[str]) -> list[re.Pattern[str]]:
    """Компилирует список regex-строк. Невалидные паттерны логируются и пропускаются."""
    compiled: list[re.Pattern[str]] = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern, re.IGNORECASE))
        except re.error:
            logger.warn(f"[cleaners] Некорректный паттерн: {pattern}")
    return compiled


def _apply_substitutions(
    text: str, substitutions: list[tuple[re.Pattern[str], str]]
) -> tuple[str, bool]:
    """Применяет список замен к тексту. Возвращает (новый текст, был ли изменён)."""
    changed = False
    for pattern, replacement in substitutions:
        new_text, count = pattern.subn(replacement, text)
        if count:
            changed = True
            text = new_text
    return text, changed


def _clean_file(
    project_root: Path,
    path: Path,
    remove_patterns: list[re.Pattern[str]],
    substitutions: list[tuple[re.Pattern[str], str]],
    generic_patterns: list[re.Pattern[str]],
) -> bool:
    """Применяет правила очистки к одному файлу.

    remove_patterns: строки удаляются целиком (robots.txt)
    substitutions: строки заменяются (readme.txt)
    generic_patterns: ссылки на домены Tilda — удаляются из любого файла
    """
    try:
        text = utils.safe_read(path)
    except Exception as exc:
        logger.warn(f"[cleaners] Пропуск {path.name}: {exc}")
        return False

    original = text

    for pattern in remove_patterns:
        text = pattern.sub("", text)

    for pattern in generic_patterns:
        text = pattern.sub("", text)

    text, changed = _apply_substitutions(text, substitutions)

    if text != original or changed:
        utils.safe_write(path, text)
        logger.info(f"🧹 Очищен файл: {utils.relpath(path, project_root)}")
        return True
    return False


def _iter_targets(project_root: Path, candidates: Iterable[str]) -> Iterable[Path]:
    """Возвращает пути файлов из списка, которые реально существуют в проекте."""
    for name in candidates:
        path = project_root / name
        if path.exists():
            yield path


def clean_text_files(project_root: Path, loader: ConfigLoader) -> CleanStats:
    """Очищает текстовые файлы проекта от артефактов Tilda.

    Какие правила применяются к каким файлам:
      robots.txt  → robots_cleanup_patterns + tilda_remnants_patterns
      readme.txt  → readme_cleanup_patterns + tilda_remnants_patterns
    """
    project_root = Path(project_root)
    patterns_cfg = loader.patterns()
    service_cfg = loader.service_files()

    robots_patterns = _compile_patterns(patterns_cfg.robots_cleanup_patterns)
    generic_patterns = _compile_patterns(patterns_cfg.tilda_remnants_patterns)

    readme_substitutions: list[tuple[re.Pattern[str], str]] = []
    for rule in patterns_cfg.readme_cleanup_patterns:
        try:
            readme_substitutions.append(
                (re.compile(rule.pattern, re.IGNORECASE), rule.replacement)
            )
        except re.error:
            logger.warn(f"[cleaners] Некорректный паттерн readme: {rule.pattern}")

    files_to_clean = service_cfg.cleaner_options.files_to_clean_tilda_refs
    stats = CleanStats()

    for path in _iter_targets(project_root, files_to_clean):
        # Каждый файл получает свой набор правил в зависимости от имени
        remove_list = robots_patterns if path.name.lower() == "robots.txt" else []
        substitutions = readme_substitutions if path.name.lower() == "readme.txt" else []
        if _clean_file(project_root, path, remove_list, substitutions, generic_patterns):
            stats.updated += 1

    return stats


def clean_project_files(
    context: ProjectContext,
    _rename_map: dict[str, str] | None = None,
) -> CleanStats:
    """Обёртка для вызова из pipeline и тестов.

    _rename_map принимается для совместимости сигнатуры, но не используется —
    очистка текстовых файлов не зависит от карты переименований.
    """
    return clean_text_files(context.project_root, context.config_loader)
