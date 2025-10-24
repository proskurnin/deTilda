# -*- coding: utf-8 -*-
"""Backwards compatible helpers around :mod:`core.configuration`.

Historically the project exposed a couple of module level functions such as
``get_patterns_config`` and ``get_rules_images`` that returned raw dictionaries.
After the refactor the configuration is represented by the
:class:`~core.configuration.DetildaConfig` class.  To avoid touching every
consumer at once this module now acts as a thin wrapper that adapts the new
objects to the legacy interfaces.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from core.configuration import ConfigRepository, ConfigSection, DetildaConfig, get_repository


def _resolve_base_dir(script_dir: str | Path | None) -> Path:
    if script_dir is None:
        return Path(__file__).resolve().parent.parent
    return Path(script_dir)


def _section_as_dict(section: ConfigSection) -> Dict[str, Any]:
    return section.as_dict()


def get_master_config(script_dir: str | Path | None = None) -> DetildaConfig:
    base_dir = _resolve_base_dir(script_dir)
    repository = get_repository(base_dir)
    return repository.load()


def get_patterns_config(script_dir: str | Path | None = None) -> Dict[str, Any]:
    repo = get_repository(_resolve_base_dir(script_dir))
    return _section_as_dict(repo.patterns())


def get_rules_images(script_dir: str | Path | None = None) -> Dict[str, Any]:
    repo = get_repository(_resolve_base_dir(script_dir))
    return _section_as_dict(repo.images())


def get_rules_service_files(script_dir: str | Path | None = None) -> Dict[str, Any]:
    repo = get_repository(_resolve_base_dir(script_dir))
    return _section_as_dict(repo.service_files())


class ConfigLoader:
    """Object oriented facade used by the refactored subsystems."""

    def __init__(self, script_dir: Path | None = None) -> None:
        self._repository = get_repository(_resolve_base_dir(script_dir))

    @property
    def repository(self) -> ConfigRepository:
        return self._repository

    @property
    def config(self) -> DetildaConfig:
        return self._repository.load()

    @property
    def patterns(self) -> ConfigSection:
        return self._repository.patterns()

    @property
    def images(self) -> ConfigSection:
        return self._repository.images()

    @property
    def service_files(self) -> ConfigSection:
        return self._repository.service_files()
