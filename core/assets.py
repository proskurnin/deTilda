# -*- coding: utf-8 -*-
"""Asset processing primitives used by the refactored pipeline."""
from __future__ import annotations
"""
assets.py — обработка ассетов Detilda v4.9 unified
Использует единый config/config.yaml:
 - patterns.assets.til_to_ai_filename — регулярка для переименования til* → ai*
 - images.delete_physical_files — списки файлов на удаление
 - service_files.exclude_from_rename — исключения из переименования
Также создаёт валидный images/1px.png (1×1 прозрачный).
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator

from core import logger
from core.configuration import iter_section_list
from core.project import ProjectContext
from core.utils import file_exists


@dataclass
class AssetStats:
    renamed: int = 0
    removed: int = 0


@dataclass
class AssetResult:
    rename_map: Dict[str, str]
    stats: AssetStats


class AssetProcessor:
    """Encapsulates the asset rename/cleanup logic."""

    def __init__(self, context: ProjectContext) -> None:
        self.context = context
        patterns = context.config_loader.patterns.as_dict()
        assets_rules = patterns.get("assets", {}) if isinstance(patterns.get("assets"), dict) else {}
        regex_pattern = assets_rules.get("til_to_ai_filename", r"\btil")
        self._til_regex = re.compile(str(regex_pattern), re.IGNORECASE)

        images_section = context.config_loader.images
        service_section = context.config_loader.service_files

        self._exclude_from_rename = {
            value.lower() for value in iter_section_list(service_section, "exclude_from_rename", "files")
        }
        self._delete_after_rename = {
            value.lower() for value in iter_section_list(images_section, "delete_physical_files", "after_rename")
        }
        self._delete_immediately = {
            value.lower() for value in iter_section_list(images_section, "delete_physical_files", "as_is")
        }

    # ---- helpers -----------------------------------------------------
    def _iter_files(self) -> Iterator[Path]:
        root = self.context.project_root
        for path in sorted(root.rglob("*")):
            if path.is_file():
                yield path

    def _sanitize_filename(self, name: str) -> str:
        sanitized = (
            name.replace(" ", "_")
            .replace("(", "")
            .replace(")", "")
            .replace(",", "")
            .replace("&", "and")
        )
        return re.sub(r"_+", "_", sanitized)

    def _rename_candidate(self, path: Path) -> Path | None:
        stem, ext = path.stem, path.suffix
        new_stem = self._til_regex.sub("ai", stem, count=1)
        if new_stem == stem:
            return None
        new_name = self._sanitize_filename(new_stem + ext)
        if new_name == path.name:
            return None
        return path.with_name(new_name)

    def _remove_file(self, path: Path, stats: AssetStats, reason: str) -> None:
        try:
            path.unlink()
            stats.removed += 1
            logger.info(f"🗑 Удалён ({reason}): {path.name}")
        except Exception as exc:
            logger.err(f"[assets] Ошибка удаления {path}: {exc}")

    def _ensure_placeholder(self) -> None:
        placeholder = self.context.project_root / "images" / "1px.png"
        if file_exists(placeholder):
            return
        data = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc``\x00\x00"
            b"\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        try:
            placeholder.parent.mkdir(parents=True, exist_ok=True)
            placeholder.write_bytes(data)
            logger.info(f"🧩 Добавлен placeholder: {self.context.relative_to_root(placeholder)}")
        except Exception as exc:
            logger.err(f"[assets] Ошибка при создании placeholder: {exc}")

    # ---- public API --------------------------------------------------
    def process(self) -> AssetResult:
        rename_map: Dict[str, str] = {}
        stats = AssetStats()

        for path in self._iter_files():
            name_lower = path.name.lower()

            if name_lower in self._delete_immediately:
                self._remove_file(path, stats, "as_is")
                continue

            if name_lower in self._exclude_from_rename:
                continue

            new_path = self._rename_candidate(path)
            if new_path:
                try:
                    old_rel = self.context.relative_to_root(path)
                    new_path = path.rename(new_path)
                    new_rel = self.context.relative_to_root(new_path)
                    rename_map[old_rel] = new_rel
                    stats.renamed += 1
                    logger.info(f"🔄 Переименован: {path.name} → {new_path.name}")
                    path = new_path
                    name_lower = path.name.lower()
                except Exception as exc:
                    logger.err(f"[assets] Ошибка переименования {path}: {exc}")
                    continue

            if name_lower in self._delete_after_rename:
                self._remove_file(path, stats, "after_rename")

        self._ensure_placeholder()
        return AssetResult(rename_map=rename_map, stats=stats)


def rename_and_cleanup_assets(context: ProjectContext) -> AssetResult:
    """Convenience wrapper used by the pipeline."""

    processor = AssetProcessor(context)
    result = processor.process()
    context.update_rename_map(result.rename_map)
    return result
