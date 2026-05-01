"""Shared project level context used by the deTilda pipeline.

ProjectContext — центральный контейнер данных для одного запуска обработки.
Создаётся один раз в DetildaPipeline.run() и передаётся во все шаги конвейера.

Содержит:
  - project_root: папка распакованного архива (_workdir/hotelsargis/)
  - repository_root: корень репозитория deTilda (где лежат config/, resources/)
  - config_loader: доступ к config.yaml
  - rename_map: карта переименований, накапливается в assets.py и используется в refs.py

Пример жизненного цикла:
  1. DetildaPipeline.run() создаёт ProjectContext через from_project_root()
  2. assets.py заполняет rename_map через update_rename_map()
  3. refs.py читает rename_map и обновляет ссылки в файлах
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

from core import logger, utils
from core.config_loader import ConfigLoader
from core.params import ProcessParams
from core.schemas import AppConfig


def _is_repository_root(path: Path) -> bool:
    return (path / "config" / "config.yaml").is_file() and (path / "resources").is_dir()


def _detect_repository_root(project_root: Path) -> Path:
    """Определяет корень репозитория, где лежат config/ и resources/.

    Web jobs распаковываются глубже обычного CLI:
      _workdir/<job_id>/<job_id>/
    Поэтому нельзя полагаться только на parent.name == "_workdir"; сначала
    ищем ближайшего предка с config/config.yaml и resources/.
    """
    project_root = Path(project_root).resolve()
    for candidate in (project_root.parent, *project_root.parents):
        if _is_repository_root(candidate):
            return candidate

    if project_root.parent.name == "_workdir":
        return project_root.parent.parent
    return project_root.parent


@dataclass
class ProjectContext:
    """Lightweight container with precomputed project level information."""

    project_root: Path       # папка с файлами сайта
    repository_root: Path    # корень deTilda (config/, resources/, logs/)
    config_loader: ConfigLoader
    rename_map: Dict[str, str] = field(default_factory=dict)  # {старый_путь: новый_путь}
    params: ProcessParams = field(default_factory=ProcessParams)  # параметры запроса

    @classmethod
    def from_project_root(
        cls,
        project_root: Path,
        params: ProcessParams | None = None,
    ) -> "ProjectContext":
        """Создаёт контекст из пути к распакованному проекту.

        Автоматически определяет repository_root и инициализирует ConfigLoader.
        """
        project_root = Path(project_root).resolve()
        repository_root = _detect_repository_root(project_root)
        loader = ConfigLoader(repository_root)
        return cls(
            project_root=project_root,
            repository_root=repository_root,
            config_loader=loader,
            params=params or ProcessParams(),
        )

    @property
    def config(self) -> AppConfig:
        """Прямой доступ к типизированному конфигу."""
        return self.config_loader.config

    def relative_to_root(self, path: Path) -> str:
        """Возвращает путь к файлу относительно project_root (для логов)."""
        return utils.relpath(path, self.project_root)

    def ensure_logs_dir(self, logs_dir: Path | None = None) -> Path:
        """Возвращает папку логов, создавая её если нужно.

        logs_dir: путь из manifest.json, переданный через DetildaPipeline.
        Если не передан — используется repository_root/logs/.
        """
        resolved = logs_dir or (self.repository_root / "logs")
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved

    def attach_logger(self, logs_dir: Path | None = None) -> None:
        """Инициализирует логгер для этого проекта.

        Вызывается сразу после создания контекста в DetildaPipeline.run().
        """
        resolved_logs_dir = self.ensure_logs_dir(logs_dir)
        logger.attach_to_project(self.project_root, logs_dir=resolved_logs_dir)

    def update_rename_map(self, mapping: Dict[str, str]) -> None:
        """Добавляет записи в карту переименований.

        Вызывается из assets.py после переименования файлов.
        Карта затем используется refs.py для обновления ссылок в HTML/CSS/JS.
        """
        self.rename_map.update(mapping)
