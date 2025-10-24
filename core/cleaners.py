# -*- coding: utf-8 -*-
"""Cleaning helpers used by the refactored pipeline."""
from __future__ import annotations
"""
cleaners.py — полная реконфигурация проекта после экспорта из Tilda
Detilda v4.9 unified: правила берутся из config/config.yaml.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from core import logger
from core.configuration import iter_section_list
from core.project import ProjectContext

_TEXT_EXTENSIONS = {".html", ".htm", ".css", ".js", ".json", ".txt", ".svg", ".md", ".php"}


@dataclass
class CleanResult:
    removed: int = 0
    updated: int = 0

    @property
    def total(self) -> int:
        return self.removed + self.updated


class Cleaner:
    def __init__(self, context: ProjectContext) -> None:
        self.context = context
        images_section = context.config_loader.images
        service_section = context.config_loader.service_files

        image_names = list(iter_section_list(images_section, "delete_physical_files", "after_rename"))
        image_names += list(iter_section_list(images_section, "delete_physical_files", "as_is"))
        service_names = list(iter_section_list(service_section, "scripts_to_delete", "after_rename"))

        self._image_names = {name.lower() for name in image_names}
        self._service_names = {name.lower() for name in service_names}
        self._patterns = self._extract_patterns(images_section.as_dict())
        self._patterns.extend(self._extract_patterns(service_section.as_dict()))

    # ---- config ------------------------------------------------------
    def _extract_patterns(self, data: Any) -> List[str]:
        patterns: List[str] = []
        if isinstance(data, dict):
            for value in data.values():
                patterns.extend(self._extract_patterns(value))
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    pattern = item.get("pattern")
                    if isinstance(pattern, str):
                        patterns.append(pattern)
        return patterns

    # ---- deletion ----------------------------------------------------
    def _should_remove(self, path: Path) -> bool:
        name = path.name.lower()
        rel_path = self.context.relative_to_root(path).lower()
        if name in self._image_names or name in self._service_names:
            return True
        for pattern in self._patterns:
            try:
                if re.search(pattern, rel_path, flags=re.IGNORECASE):
                    return True
            except re.error:
                logger.warn(f"[cleaners] Некорректный паттерн удаления: {pattern}")
        return False

    def _delete_files(self) -> int:
        removed = 0
        for path in self.context.project_root.rglob("*"):
            if not path.is_file():
                continue
            if self._should_remove(path):
                try:
                    path.unlink()
                    removed += 1
                    logger.info(f"🗑 Удалён по правилу: {path.name}")
                except Exception as exc:
                    logger.err(f"[cleaners] Ошибка удаления {path}: {exc}")
        return removed

    # ---- updates -----------------------------------------------------
    def _update_links(self, rename_map: Dict[str, str]) -> int:
        if not rename_map:
            return 0
        updated = 0
        for path in self.context.project_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _TEXT_EXTENSIONS:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception as exc:
                logger.err(f"[cleaners] Ошибка чтения {path}: {exc}")
                continue
            original = text
            for old_rel, new_rel in rename_map.items():
                text = text.replace(old_rel, new_rel)
            if text != original:
                try:
                    path.write_text(text, encoding="utf-8")
                    updated += 1
                    logger.info(f"🔗 Обновлены ссылки: {self.context.relative_to_root(path)}")
                except Exception as exc:
                    logger.err(f"[cleaners] Ошибка записи {path}: {exc}")
        return updated

    def _save_rename_map(self, rename_map: Dict[str, str]) -> None:
        if not rename_map:
            return
        target = self.context.project_root / "rename_map.json"
        try:
            target.write_text(
                json.dumps(rename_map, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            logger.ok(
                "💾 Таблица маппинга сохранена: rename_map.json "
                f"({len(rename_map)} элементов)"
            )
        except Exception as exc:
            logger.err(f"[cleaners] Ошибка сохранения rename_map.json: {exc}")

    # ---- public API --------------------------------------------------
    def run(self, rename_map: Dict[str, str]) -> CleanResult:
        logger.info("🧹 Запуск очистки и реконфигурации проекта...")
        removed = self._delete_files()
        updated = self._update_links(rename_map)
        self._save_rename_map(rename_map)
        logger.ok(
            f"✅ Очистка завершена. Удалено {removed}, обновлено {updated} файлов."
        )
        return CleanResult(removed=removed, updated=updated)


def clean_project_files(context: ProjectContext, rename_map: Dict[str, str]) -> CleanResult:
    cleaner = Cleaner(context)
    return cleaner.run(rename_map)
