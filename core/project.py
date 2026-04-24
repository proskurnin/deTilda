"""Shared project level context used by the deTilda pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

from core import logger, utils
from core.config_loader import ConfigLoader
from core.schemas import AppConfig


def _detect_repository_root(project_root: Path) -> Path:
    """Return the directory that holds configuration and resources."""
    if project_root.parent.name == "_workdir":
        return project_root.parent.parent
    return project_root.parent


@dataclass
class ProjectContext:
    """Lightweight container with precomputed project level information."""

    project_root: Path
    repository_root: Path
    config_loader: ConfigLoader
    rename_map: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_project_root(cls, project_root: Path) -> "ProjectContext":
        project_root = Path(project_root).resolve()
        repository_root = _detect_repository_root(project_root)
        loader = ConfigLoader(repository_root)
        return cls(
            project_root=project_root,
            repository_root=repository_root,
            config_loader=loader,
        )

    @property
    def config(self) -> AppConfig:
        return self.config_loader.config

    def relative_to_root(self, path: Path) -> str:
        return utils.relpath(path, self.project_root)

    def ensure_logs_dir(self, logs_dir: Path | None = None) -> Path:
        """Return logs directory — from argument or manifest default."""
        resolved = logs_dir or (self.repository_root / "logs")
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved

    def attach_logger(self, logs_dir: Path | None = None) -> None:
        resolved_logs_dir = self.ensure_logs_dir(logs_dir)
        logger.attach_to_project(self.project_root, logs_dir=resolved_logs_dir)

    def update_rename_map(self, mapping: Dict[str, str]) -> None:
        self.rename_map.update(mapping)
