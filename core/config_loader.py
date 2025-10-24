# -*- coding: utf-8 -*-
"""
config_loader.py — модуль загрузки конфигурационных файлов Detilda v4.2 LTS
Загружает и кэширует YAML/JSON конфиги из папки config/, обеспечивает
совместимость путей для работы со строками и pathlib.Path.
"""

import os
import json
import yaml
from pathlib import Path
from core import logger


# === Кэш, чтобы не грузить конфиги повторно ===
_CACHE = {}


# === Универсальная функция загрузки YAML ===
def _load_yaml(path: Path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.err(f"[config_loader] Файл не найден: {path}")
        return {}
    except Exception as e:
        logger.err(f"[config_loader] Ошибка при чтении YAML {path}: {e}")
        return {}


# === Универсальная функция загрузки JSON ===
def _load_json(path: Path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.err(f"[config_loader] Файл не найден: {path}")
        return {}
    except json.JSONDecodeError as e:
        logger.err(f"[config_loader] Ошибка JSON-декодирования в {path}: {e}")
        return {}
    except Exception as e:
        logger.err(f"[config_loader] Ошибка при чтении JSON {path}: {e}")
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


# === Универсальная функция загрузки конфигов с кэшированием ===
def _get_config(script_dir: str | Path, filename: str, is_yaml: bool = True):
    script_dir = Path(script_dir)
    config_path = script_dir / "config" / filename

    if config_path in _CACHE:
        return _CACHE[config_path]

    if not config_path.exists():
        logger.err(f"[config_loader] Конфиг не найден: {config_path}")
        return {}

    cfg = _load_yaml(config_path) if is_yaml else _load_json(config_path)
    _compile_regex(cfg)
    _CACHE[config_path] = cfg
    return cfg


# === Публичные функции ===
def get_patterns_config(script_dir: str | Path):
    """Загружает patterns.yaml"""
    return _get_config(script_dir, "patterns.yaml", is_yaml=True)


def get_rules_images(script_dir: str | Path):
    """Загружает rules_images.json"""
    return _get_config(script_dir, "rules_images.json", is_yaml=False)


def get_rules_service_files(script_dir: str | Path):
    """Загружает rules_service_files.json"""
    return _get_config(script_dir, "rules_service_files.json", is_yaml=False)


# === Для отладки ===
if __name__ == "__main__":
    test_dir = Path(__file__).resolve().parent.parent
    try:
        patterns = get_patterns_config(test_dir)
        images = get_rules_images(test_dir)
        service = get_rules_service_files(test_dir)

        logger.info("✅ Конфиги успешно загружены:")
        logger.info(f"  • patterns.yaml: {len(patterns)} ключей")
        logger.info(f"  • rules_images.json: {len(images)} ключей")
        logger.info(f"  • rules_service_files.json: {len(service)} ключей")
    except Exception as e:
        logger.err(f"💥 Ошибка при тестовой загрузке конфигов: {e}")