"""Utilities for working with the Detilda configuration file.

This module provides small dataclasses that describe the structure of the
`config/config.yaml` file.  The goal of the refactor is to avoid passing raw
nested dictionaries around the codebase – every consumer receives a
`DetildaConfig` instance and works with typed `ConfigSection` wrappers instead.

The classes here are intentionally lightweight: they do not try to validate all
possible schema options but they do provide a predictable mapping interface and
helper accessors used throughout the pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Mapping, MutableMapping

import yaml

from core import logger


def _as_dict(data: Any) -> Dict[str, Any]:
    """Return a shallow copy of *data* if it is a mapping."""
    if isinstance(data, Mapping):
        return dict(data)
    return {}


@dataclass(frozen=True)
class ConfigSection(Mapping[str, Any]):
    """Immutable dictionary-like view over one section of the config."""

    name: str
    data: Mapping[str, Any] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:  # type: ignore[override]
        return _as_dict(self.data).get(key)

    def __iter__(self) -> Iterator[str]:  # type: ignore[override]
        return iter(_as_dict(self.data))

    def __len__(self) -> int:  # type: ignore[override]
        return len(_as_dict(self.data))

    def get(self, key: str, default: Any = None) -> Any:
        return _as_dict(self.data).get(key, default)

    def get_list(self, key: str) -> list[Any]:
        value = self.get(key, [])
        if isinstance(value, list):
            return list(value)
        return []

    def get_nested_list(self, *keys: str) -> list[Any]:
        current: Any = _as_dict(self.data)
        for key in keys:
            if not isinstance(current, Mapping):
                return []
            current = current.get(key)
        if isinstance(current, list):
            return list(current)
        return []

    def as_dict(self) -> Dict[str, Any]:
        return _as_dict(self.data)


@dataclass(frozen=True)
class DetildaConfig:
    """High level view over `config/config.yaml`."""

    path: Path
    raw: Mapping[str, Any]
    patterns: ConfigSection = field(init=False)
    images: ConfigSection = field(init=False)
    service_files: ConfigSection = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "patterns", ConfigSection("patterns", _as_dict(self.raw.get("patterns"))))
        object.__setattr__(self, "images", ConfigSection("images", _as_dict(self.raw.get("images"))))
        object.__setattr__(self, "service_files", ConfigSection("service_files", _as_dict(self.raw.get("service_files"))))

    @classmethod
    def from_path(cls, config_path: Path) -> "DetildaConfig":
        try:
            with config_path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
                if not isinstance(data, MutableMapping):
                    logger.err(f"[configuration] Некорректный формат YAML: {config_path}")
                    data = {}
        except FileNotFoundError:
            logger.err(f"[configuration] Файл не найден: {config_path}")
            data = {}
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.err(f"[configuration] Ошибка при чтении {config_path}: {exc}")
            data = {}
        return cls(path=config_path, raw=dict(data))

    def section(self, name: str) -> ConfigSection:
        name = name.lower()
        if name == "patterns":
            return self.patterns
        if name == "images":
            return self.images
        if name == "service_files":
            return self.service_files
        return ConfigSection(name, _as_dict(self.raw.get(name, {})))


class ConfigRepository:
    """Lazy configuration loader with a small in-memory cache."""

    def __init__(self, script_dir: Path, filename: str = "config.yaml") -> None:
        self._script_dir = script_dir
        self._filename = filename
        self._cache: DetildaConfig | None = None

    @property
    def config_path(self) -> Path:
        return self._script_dir / "config" / self._filename

    def load(self) -> DetildaConfig:
        if self._cache is None:
            self._cache = DetildaConfig.from_path(self.config_path)
        return self._cache

    def section(self, name: str) -> ConfigSection:
        return self.load().section(name)

    def patterns(self) -> ConfigSection:
        return self.section("patterns")

    def images(self) -> ConfigSection:
        return self.section("images")

    def service_files(self) -> ConfigSection:
        return self.section("service_files")


_DEFAULT_SCRIPT_DIR = Path(__file__).resolve().parent.parent
_default_repository = ConfigRepository(_DEFAULT_SCRIPT_DIR)


def get_repository(script_dir: Path | None = None) -> ConfigRepository:
    if script_dir is None:
        return _default_repository
    return ConfigRepository(Path(script_dir))


def load_config(script_dir: Path | None = None) -> DetildaConfig:
    return get_repository(script_dir).load()


def iter_section_list(section: ConfigSection, *keys: str) -> Iterable[str]:
    """Helper used across modules to read nested lists of filenames."""
    for value in section.get_nested_list(*keys):
        if isinstance(value, str):
            yield value
