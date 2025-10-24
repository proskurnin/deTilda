# -*- coding: utf-8 -*-
"""
config_loader.py — модуль загрузки конфигурационных файлов Detilda v4.9 unified
Загружает единый YAML-конфиг из папки config/, кэширует его и предоставляет
функции доступа к основным разделам (patterns, images, service_files).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from core import logger


# === Путь по умолчанию и кэш, чтобы не грузить конфиги повторно ===
_DEFAULT_SCRIPT_DIR = Path(__file__).resolve().parent.parent
_CONFIG_FILENAME = "config.yaml"
_CACHE: Dict[Path, Dict[str, Any]] = {}


# === Универсальная функция загрузки YAML ===
def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                logger.err(f"[config_loader] Некорректный формат YAML: {path}")
                return {}
            return data
    except FileNotFoundError:
        logger.err(f"[config_loader] Файл не найден: {path}")
        return {}
    except Exception as e:
        logger.err(f"[config_loader] Ошибка при чтении YAML {path}: {e}")
        return {}


# === Компиляция регулярных выражений, если нужно ===
def _compile_regex(cfg):
    import re
    for key, val in cfg.items():
        if isinstance(val, str):
            try:
                re.compile(val)
            except re.error:
                pass
        elif isinstance(val, list):
            for i, v in enumerate(val):
                if isinstance(v, str):
                    try:
                        re.compile(v)
                    except re.error:
                        pass
        elif isinstance(val, dict):
            _compile_regex(val)


# === Вспомогательные функции ===
def _resolve_base_dir(script_dir: str | Path | None) -> Path:
    if script_dir is None:
        return _DEFAULT_SCRIPT_DIR
    return Path(script_dir)


def _get_config(script_dir: str | Path | None, filename: str) -> Dict[str, Any]:
    base_dir = _resolve_base_dir(script_dir)
    config_path = base_dir / "config" / filename

    if config_path in _CACHE:
        return _CACHE[config_path]

    if not config_path.exists():
        logger.err(f"[config_loader] Конфиг не найден: {config_path}")
        return {}

    cfg = _load_yaml(config_path)
    _compile_regex(cfg)
    _CACHE[config_path] = cfg
    return cfg


# === Публичные функции ===
def get_master_config(script_dir: str | Path | None = None) -> Dict[str, Any]:
    """Возвращает полный конфиг config.yaml."""
    return _get_config(script_dir, _CONFIG_FILENAME)


def _get_section(script_dir: str | Path | None, section: str) -> Dict[str, Any]:
    cfg = get_master_config(script_dir)
    data = cfg.get(section, {}) if isinstance(cfg, dict) else {}
    if isinstance(data, dict):
        _compile_regex(data)
        return data
    logger.warn(f"[config_loader] Секция '{section}' имеет некорректный формат")
    return {}


def get_patterns_config(script_dir: str | Path | None = None) -> Dict[str, Any]:
    """Возвращает секцию patterns из config.yaml."""
    return _get_section(script_dir, "patterns")


def get_rules_images(script_dir: str | Path | None = None) -> Dict[str, Any]:
    """Возвращает секцию images из config.yaml."""
    return _get_section(script_dir, "images")


def get_rules_service_files(script_dir: str | Path | None = None) -> Dict[str, Any]:
    """Возвращает секцию service_files из config.yaml."""
    return _get_section(script_dir, "service_files")


# === Для отладки ===
if __name__ == "__main__":
    test_dir = Path(__file__).resolve().parent.parent
    try:
        master = get_master_config(test_dir)
        patterns = get_patterns_config(test_dir)
        images = get_rules_images(test_dir)
        service = get_rules_service_files(test_dir)

        logger.info("✅ Конфиг успешно загружен:")
        logger.info(f"  • config.yaml: {len(master)} разделов")
        logger.info(f"  • patterns: {len(patterns)} ключей")
        logger.info(f"  • images: {len(images)} ключей")
        logger.info(f"  • service_files: {len(service)} ключей")
    except Exception as e:
        logger.err(f"💥 Ошибка при тестовой загрузке конфигов: {e}")