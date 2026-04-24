"""Typed access helpers for :mod:`config/config.yaml`."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml
from core.pydantic_compat import ValidationError

from core import logger
from core.schemas import (
    AppConfig,
    ImagesConfig,
    PatternsConfig,
    ServiceFilesConfig,
    validate_regex_patterns,
)

_DEFAULT_BASE_DIR = Path(__file__).resolve().parent.parent


def _normalize_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Pre-process raw YAML before passing to Pydantic.

    Normalises readme_cleanup_patterns so every item is a dict
    with 'pattern' and 'replacement' keys — Pydantic then maps
    them cleanly to ReplaceRule objects.
    """
    patterns = data.get("patterns")
    if not isinstance(patterns, dict):
        return data

    raw = patterns.get("readme_cleanup_patterns", [])
    if not isinstance(raw, list):
        return data

    normalized = []
    for item in raw:
        if isinstance(item, str):
            normalized.append({"pattern": item, "replacement": ""})
        elif isinstance(item, dict):
            normalized.append(item)
        else:
            normalized.append(item)

    patterns["readme_cleanup_patterns"] = normalized
    return data


def _validate_config(data: Dict[str, Any]) -> AppConfig:
    data = _normalize_data(data)
    if hasattr(AppConfig, "model_validate"):
        return AppConfig.model_validate(data)  # type: ignore[attr-defined]
    return AppConfig.parse_obj(data)


class ConfigLoader:
    """Loads and caches the unified ``config.yaml`` file."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or _DEFAULT_BASE_DIR
        self._cache: AppConfig | None = None

    @property
    def base_dir(self) -> Path:
        return Path(self._base_dir)

    @property
    def config_path(self) -> Path:
        return Path(self._base_dir) / "config" / "config.yaml"

    def _load(self) -> AppConfig:
        if self._cache is not None:
            return self._cache

        path = self.config_path
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                raise ValueError("config.yaml должен содержать словарь")
            config = _validate_config(data)
            for error in validate_regex_patterns(config):
                logger.warn(f"[config_loader] {error}")
        except FileNotFoundError:
            logger.err(f"[config_loader] Не найден файл конфигурации: {path}")
            config = AppConfig()
        except ValidationError as exc:
            logger.err(f"[config_loader] Ошибка валидации {path}: {exc}")
            config = AppConfig()
        except Exception as exc:
            logger.err(f"[config_loader] Ошибка чтения {path}: {exc}")
            config = AppConfig()

        self._cache = config
        return config

    @property
    def config(self) -> AppConfig:
        return self._load()

    def patterns(self) -> PatternsConfig:
        return self._load().patterns

    def images(self) -> ImagesConfig:
        return self._load().images

    def service_files(self) -> ServiceFilesConfig:
        return self._load().service_files
