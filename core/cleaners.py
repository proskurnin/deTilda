# -*- coding: utf-8 -*-
"""
cleaners.py — полная реконфигурация проекта после экспорта из Tilda
Detilda v4.9 unified: правила берутся из config/config.yaml.
"""

import json
import os
import re
from pathlib import Path
from core import logger, config_loader


# === Вспомогательные функции ===

def _project_base_dir(project_root: Path) -> Path:
    """Возвращает корень репозитория с конфигурацией."""
    return project_root.parent.parent if project_root.parent.name == "_workdir" else project_root.parent


def _collect_delete_patterns(images_cfg: dict) -> list[str]:
    targets = []
    block = images_cfg.get("delete_physical_files", {}) if isinstance(images_cfg, dict) else {}
    for key in ("after_rename", "as_is"):
        items = block.get(key, []) if isinstance(block, dict) else []
        targets.extend(str(item) for item in (items or []))
    return targets


def _collect_service_deletions(service_cfg: dict) -> list[str]:
    targets = []
    block = service_cfg.get("scripts_to_delete", {}) if isinstance(service_cfg, dict) else {}
    items = block.get("after_rename", []) if isinstance(block, dict) else []
    targets.extend(str(item) for item in (items or []))
    return targets


def _load_rules(project_root: Path) -> dict:
    """
    Загружает правила удаления файлов из конфигов.
    """
    rules = {"images": [], "service": []}
    try:
        base_dir = _project_base_dir(project_root)
        images_cfg = config_loader.get_rules_images(base_dir)
        service_cfg = config_loader.get_rules_service_files(base_dir)

        rules["images"] = _collect_delete_patterns(images_cfg)
        rules["service"] = _collect_service_deletions(service_cfg)

        logger.info(f"⚙️ Загружены правила удаления изображений: {len(rules['images'])}")
        logger.info(f"⚙️ Загружены правила удаления сервисных файлов: {len(rules['service'])}")
    except Exception as e:
        logger.err(f"[cleaners] Ошибка загрузки правил: {e}")
    return rules


def _match_any_rule(filename: str, rules: list) -> bool:
    """
    Проверяет, совпадает ли имя файла с каким-либо правилом.
    """
    for rule in rules:
        if isinstance(rule, str):
            pattern = rule
        elif isinstance(rule, dict):
            pattern = rule.get("pattern") or rule.get("name")
        else:
            continue

        try:
            if re.search(pattern, filename, flags=re.I):
                return True
        except re.error:
            continue
    return False


def _rename_tilda_files(project_root: Path) -> dict:
    """
    Переименовывает все файлы вида til* → ai*.
    Возвращает словарь маппинга {старое: новое}.
    """
    rename_map = {}
    for file in project_root.rglob("*"):
        if not file.is_file():
            continue
        if file.name.startswith("til"):
            new_name = "ai" + file.name[3:]
            new_path = file.with_name(new_name)
            try:
                file.rename(new_path)
                rename_map[file.name] = new_name
                logger.info(f"🧩 Переименован: {file.name} → {new_name}")
            except Exception as e:
                logger.err(f"[cleaners] Ошибка переименования {file}: {e}")
    return rename_map


def _update_links_in_file(file_path: Path, rename_map: dict) -> bool:
    """
    Обновляет все ссылки в файле по карте переименования.
    Возвращает True, если были изменения.
    """
    ext = file_path.suffix.lower()
    if ext not in [".html", ".htm", ".css", ".js", ".json", ".txt", ".svg", ".md"]:
        return False

    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        logger.err(f"[cleaners] Ошибка чтения {file_path}: {e}")
        return False

    orig = text
    for old, new in rename_map.items():
        text = text.replace(old, new)

    if text != orig:
        try:
            file_path.write_text(text, encoding="utf-8")
            logger.info(f"🔗 Обновлены ссылки: {file_path.relative_to(file_path.parents[2])}")
            return True
        except Exception as e:
            logger.err(f"[cleaners] Ошибка записи {file_path}: {e}")
    return False


def _remove_files_by_rules(project_root: Path, rules: dict) -> int:
    """
    Удаляет файлы, подпадающие под правила.
    """
    removed = 0
    for file in project_root.rglob("*"):
        if not file.is_file():
            continue
        if _match_any_rule(file.name, rules["images"]) or _match_any_rule(file.name, rules["service"]):
            try:
                os.remove(file)
                removed += 1
                logger.info(f"🗑 Удалён по правилу: {file.name}")
            except Exception as e:
                logger.err(f"[cleaners] Ошибка удаления {file}: {e}")
    return removed


# === Основная функция ===

def clean_project_files(project_root: Path) -> int:
    """
    Полный цикл очистки и реконфигурации проекта:
    1. Загрузка правил удаления.
    2. Удаление ненужных файлов.
    3. Переименование til* → ai*.
    4. Обновление ссылок во всех текстовых файлах.
    5. Сохранение карты маппинга (rename_map.json).
    """
    if not project_root.exists():
        logger.err(f"⚠️ Папка проекта {project_root} не найдена.")
        return 0

    logger.info("🧹 Запуск очистки и реконфигурации проекта...")

    # 1️⃣ Загрузка правил
    rules = _load_rules(project_root)

    # 2️⃣ Удаление мусора
    removed_count = _remove_files_by_rules(project_root, rules)

    # 3️⃣ Переименование файлов
    rename_map = _rename_tilda_files(project_root)

    # 4️⃣ Обновление ссылок
    changed_files = 0
    for file in project_root.rglob("*"):
        if _update_links_in_file(file, rename_map):
            changed_files += 1

    # 5️⃣ Сохранение карты
    try:
        rename_map_path = project_root / "rename_map.json"
        rename_map_path.write_text(
            json.dumps(rename_map, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        logger.ok(f"💾 Таблица маппинга сохранена: rename_map.json ({len(rename_map)} элементов)")
    except Exception as e:
        logger.err(f"[cleaners] Ошибка сохранения rename_map.json: {e}")

    total_changed = changed_files + removed_count
    logger.ok(f"✅ Очистка завершена. Удалено {removed_count}, обновлено {changed_files} файлов.")
    return total_changed