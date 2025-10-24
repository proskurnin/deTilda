"""Lightweight access helpers for :mod:`config/config.yaml`."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Iterator

import yaml

from core import logger

_DEFAULT_BASE_DIR = Path(__file__).resolve().parent.parent


class ConfigLoader:
    """Loads and caches the unified ``config.yaml`` file."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or _DEFAULT_BASE_DIR
        self._cache: Dict[str, Any] | None = None

    # ------------------------------------------------------------------
    @property
    def base_dir(self) -> Path:
        return Path(self._base_dir)

    @property
    def config_path(self) -> Path:
        return Path(self._base_dir) / "config" / "config.yaml"

    def _load(self) -> Dict[str, Any]:
        if self._cache is not None:
            return self._cache
        path = self.config_path
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                raise ValueError("config.yaml должен содержать словарь")
        except FileNotFoundError:
            logger.err(f"[config_loader] Не найден файл конфигурации: {path}")
            data = {}
        except Exception as exc:  # pragma: no cover - defensive branch
            logger.err(f"[config_loader] Ошибка чтения {path}: {exc}")
            data = {}
        self._cache = data
        return data

    def as_dict(self) -> Dict[str, Any]:
        return dict(self._load())

    # ------------------------------------------------------------------
    def patterns(self) -> Dict[str, Any]:
        return dict(self._load().get("patterns", {}))

    def images(self) -> Dict[str, Any]:
        return dict(self._load().get("images", {}))

    def service_files(self) -> Dict[str, Any]:
        return dict(self._load().get("service_files", {}))


# ----------------------------------------------------------------------------
# Backwards compatible module level helpers
# ----------------------------------------------------------------------------
_loader = ConfigLoader()


def get_master_config(script_dir: str | Path | None = None) -> Dict[str, Any]:
    loader = ConfigLoader(Path(script_dir) if script_dir else None)
    return loader.as_dict()


def get_patterns_config(script_dir: str | Path | None = None) -> Dict[str, Any]:
    loader = ConfigLoader(Path(script_dir) if script_dir else None)
    return loader.patterns()


def get_rules_images(script_dir: str | Path | None = None) -> Dict[str, Any]:
    loader = ConfigLoader(Path(script_dir) if script_dir else None)
    return loader.images()


def get_rules_service_files(script_dir: str | Path | None = None) -> Dict[str, Any]:
    loader = ConfigLoader(Path(script_dir) if script_dir else None)
    return loader.service_files()


def iter_section_list(section: Dict[str, Any], *keys: str) -> Iterator[str]:
    current: Any = section
    for key in keys:
        if not isinstance(current, dict):
            return iter(())
        current = current.get(key)
    values: Iterable[Any]
    if isinstance(current, list):
        values = current
    else:
        values = []
    return [value for value in values if isinstance(value, str)]
