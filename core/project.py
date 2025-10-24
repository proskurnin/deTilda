"""Shared project level context used by the refactored pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

from core import logger
from core.config_loader import ConfigLoader


def _detect_repository_root(project_root: Path) -> Path:
    """Return the directory that holds the configuration file."""
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
    def config(self):
        return self.config_loader.config

    def relative_to_root(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.project_root)).replace("\\", "/")
        except ValueError:
            return path.name

    def ensure_logs_dir(self) -> Path:
        logs_dir = self.repository_root / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir

    def attach_logger(self) -> None:
        logger.attach_to_project(self.project_root)

    def update_rename_map(self, mapping: Dict[str, str]) -> None:
        self.rename_map.update(mapping)
