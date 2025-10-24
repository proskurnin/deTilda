# -*- coding: utf-8 -*-
"""
assets.py — обработка ассетов Detilda v4.9 unified
Использует единый config/config.yaml:
 - patterns.assets.til_to_ai_filename — регулярка для переименования til* → ai*
 - images.delete_physical_files — списки файлов на удаление
 - service_files.exclude_from_rename — исключения из переименования
Также создаёт валидный images/1px.png (1×1 прозрачный).
"""

import re
from pathlib import Path
from core import logger, config_loader
from core.utils import file_exists

# Где ищем ассеты (деревья с медиа)
_ASSET_DIRS = ("images", "img", "files", "media")
# Где обычно лежат стили/скрипты
_CODE_DIRS = ("css", "js")

# Валидный 1×1 PNG (прозрачный)
_ONEPX_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc``\x00\x00"
    b"\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
)

def _project_base_dir(project_root: Path) -> Path:
    return project_root.parent.parent if project_root.parent.name == "_workdir" else project_root.parent

def _load_configs(project_root: Path) -> tuple[dict, dict, dict]:
    base_dir = _project_base_dir(project_root)
    patterns = config_loader.get_patterns_config(base_dir)
    rules_images = config_loader.get_rules_images(base_dir)
    rules_service = config_loader.get_rules_service_files(base_dir)
    return patterns, rules_images, rules_service

def _compile_til_to_ai_regex(patterns: dict) -> re.Pattern:
    # В YAML: assets.til_to_ai_filename, по умолчанию \btil
    p = None
    try:
        p = patterns.get("assets", {}).get("til_to_ai_filename", r"\btil")
    except Exception:
        p = r"\btil"
    return re.compile(p, re.IGNORECASE)

def _excluded_from_rename(rules_service: dict) -> set[str]:
    try:
        items = rules_service.get("exclude_from_rename", {}).get("files", []) or []
        return {s.lower() for s in items}
    except Exception:
        return set()

def _delete_lists(rules_images: dict) -> tuple[set[str], set[str]]:
    try:
        after_rename = set((rules_images.get("delete_physical_files", {}).get("after_rename", []) or []))
        as_is = set((rules_images.get("delete_physical_files", {}).get("as_is", []) or []))
        return {s.lower() for s in after_rename}, {s.lower() for s in as_is}
    except Exception:
        return set(), set()

def _sanitize_filename(name: str) -> str:
    out = (name.replace(" ", "_")
               .replace("(", "")
               .replace(")", "")
               .replace(",", "")
               .replace("&", "and"))
    out = re.sub(r"_+", "_", out)
    return out

def _iter_candidate_files(project_root: Path):
    """
    Итератор по файлам, которые нужно рассматривать для переименования:
    - всё в папках изображений/файлов
    - все *.css и *.js в проекте (включая /css и /js)
    """
    root = Path(project_root)
    yielded = set()

    # Медиа-папки
    for d in _ASSET_DIRS:
        base = root / d
        if base.exists():
            for p in base.rglob("*.*"):
                if p.is_file():
                    rp = p.resolve()
                    if rp not in yielded:
                        yielded.add(rp)
                        yield p

    # Все CSS/JS по всему проекту
    for pattern in ("*.css", "*.js"):
        for p in root.rglob(pattern):
            if p.is_file():
                rp = p.resolve()
                if rp not in yielded:
                    yielded.add(rp)
                    yield p

def rename_and_cleanup_assets(project_root: Path, stats: dict):
    """
    Переименовывает ассеты по правилу til* → ai*, учитывая исключения и списки удаления.
    Также переименовывает *.css и *.js файлы (именно имена файлов), и формирует rename_map.
    Возвращает:
      rename_map — {старый_относит_путь: новый_относит_путь}
      stats — {"renamed": int, "removed": int}
    """
    patterns, rules_images, rules_service = _load_configs(project_root)
    til_to_ai_rx = _compile_til_to_ai_regex(patterns)
    exclude = _excluded_from_rename(rules_service)
    del_after_rename, del_as_is = _delete_lists(rules_images)

    rename_map: dict[str, str] = {}
    renamed_count = 0
    removed_count = 0

    root = Path(project_root)

    for path in _iter_candidate_files(root):
        rel_old = str(path.relative_to(root)).replace("\\", "/")
        name_lower = path.name.lower()

        # 0) немедленное удаление "как есть"
        if name_lower in del_as_is:
            try:
                path.unlink()
                removed_count += 1
                logger.info(f"🗑 Удалён (as_is): {path.name}")
            except Exception as e:
                logger.err(f"[assets] Ошибка удаления {path}: {e}")
            continue

        # 1) исключения из переименования
        if name_lower in exclude:
            continue

        # 2) применяем til* → ai* на ИМЕНИ файла
        stem, ext = path.stem, path.suffix
        new_stem = til_to_ai_rx.sub("ai", stem, count=1)  # только первый префикс
        new_name = _sanitize_filename(new_stem + ext)

        if new_name != path.name:
            new_path = path.with_name(new_name)
            try:
                path.rename(new_path)
                renamed_count += 1
                rel_new = str(new_path.relative_to(root)).replace("\\", "/")
                rename_map[rel_old] = rel_new
                logger.info(f"🔄 Переименован: {path.name} → {new_name}")
                path = new_path
                name_lower = new_name.lower()
                rel_old = rel_new
            except Exception as e:
                logger.err(f"[assets] Ошибка переименования {path}: {e}")

        # 3) удаление «после переименования»
        if name_lower in del_after_rename:
            try:
                path.unlink()
                removed_count += 1
                logger.info(f"🗑 Удалён (after_rename): {path.name}")
            except Exception as e:
                logger.err(f"[assets] Ошибка удаления {path}: {e}")
            continue

    # 4) placeholder 1px.png
    placeholder = root / "images" / "1px.png"
    if not file_exists(placeholder):
        try:
            placeholder.parent.mkdir(parents=True, exist_ok=True)
            with open(placeholder, "wb") as f:
                f.write(_ONEPX_PNG)
            logger.info(f"🧩 Добавлен placeholder: {placeholder}")
        except Exception as e:
            logger.err(f"[assets] Ошибка при создании placeholder: {e}")

    stats["renamed"] = renamed_count
    stats["removed"] = removed_count
    logger.info(f"📦 Ассеты обработаны: переименовано {renamed_count}, удалено {removed_count}")
    return rename_map, stats