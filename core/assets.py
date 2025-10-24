"""Asset rename and cleanup utilities."""
from __future__ import annotations

import re
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from core import logger, utils
from core.config_loader import ConfigLoader, iter_section_list

__all__ = ["AssetStats", "rename_and_cleanup_assets"]


@dataclass
class AssetStats:
    renamed: int = 0
    removed: int = 0


@dataclass
class AssetResult:
    rename_map: Dict[str, str]
    stats: AssetStats


def _collect_lowercase_names(section: Dict[str, object], *keys: str) -> set[str]:
    return {name.lower() for name in iter_section_list(section, *keys)}


def _sanitize(name: str) -> str:
    sanitized = (
        name.replace(" ", "_")
        .replace("(", "")
        .replace(")", "")
        .replace(",", "")
        .replace("&", "and")
    )
    return re.sub(r"_+", "_", sanitized)


def rename_and_cleanup_assets(project_root: Path, loader: ConfigLoader) -> AssetResult:
    project_root = Path(project_root)
    patterns_cfg = loader.patterns()
    images_cfg = loader.images()
    service_cfg = loader.service_files()

    regex_pattern = (
        patterns_cfg.get("assets", {}).get("til_to_ai_filename")
        if isinstance(patterns_cfg.get("assets"), dict)
        else None
    )
    til_regex = re.compile(str(regex_pattern or r"\btil"), re.IGNORECASE)

    exclude_from_rename = _collect_lowercase_names(service_cfg, "exclude_from_rename", "files")
    delete_after_rename = _collect_lowercase_names(images_cfg, "delete_physical_files", "after_rename")
    delete_immediately = _collect_lowercase_names(images_cfg, "delete_physical_files", "as_is")
    delete_service = _collect_lowercase_names(service_cfg, "scripts_to_delete", "after_rename")

    rename_map: Dict[str, str] = {}
    stats = AssetStats()

    for path in sorted(project_root.rglob("*")):
        if not path.is_file():
            continue

        name_lower = path.name.lower()

        if name_lower in delete_immediately or name_lower in delete_service:
            try:
                path.unlink()
                stats.removed += 1
                logger.info(f"🗑 Удалён (as_is): {path.name}")
            except Exception as exc:
                logger.err(f"[assets] Ошибка удаления {path}: {exc}")
            continue

        if name_lower in exclude_from_rename:
            continue

        new_name = path.name
        match = til_regex.search(path.stem)
        if match:
            new_name = _sanitize(til_regex.sub("ai", path.stem, count=1) + path.suffix)

        if new_name != path.name:
            new_path = path.with_name(new_name)
            try:
                old_rel = utils.relpath(path, project_root)
                path = path.rename(new_path)
                new_rel = utils.relpath(new_path, project_root)
                rename_map[old_rel] = new_rel
                stats.renamed += 1
                logger.info(f"🔄 Переименован: {old_rel} → {new_rel}")
                name_lower = new_path.name.lower()
            except Exception as exc:
                logger.err(f"[assets] Ошибка переименования {path}: {exc}")
                continue

        if name_lower in delete_after_rename or name_lower in delete_service:
            try:
                path.unlink()
                stats.removed += 1
                logger.info(f"🗑 Удалён (after_rename): {path.name}")
            except Exception as exc:
                logger.err(f"[assets] Ошибка удаления {path}: {exc}")

    placeholder = project_root / "images" / "1px.png"
    if not placeholder.exists():
        placeholder.parent.mkdir(parents=True, exist_ok=True)
        placeholder.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc``\x00\x00"
            b"\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        logger.info(f"🧩 Добавлен placeholder: {utils.relpath(placeholder, project_root)}")

    if rename_map:
        mapping_path = project_root / "rename_map.json"
        try:
            utils.safe_write(
                mapping_path,
                json.dumps(rename_map, ensure_ascii=False, indent=2, sort_keys=True),
            )
            logger.ok(
                f"💾 Таблица маппинга сохранена: {mapping_path.name} ({len(rename_map)} элементов)"
            )
        except Exception as exc:
            logger.err(f"[assets] Ошибка сохранения rename_map.json: {exc}")

    logger.info(
        f"📦 Ассеты обработаны: переименовано {stats.renamed}, удалено {stats.removed}"
    )
    return AssetResult(rename_map=rename_map, stats=stats)
