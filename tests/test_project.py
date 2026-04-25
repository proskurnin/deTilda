"""Tests for core.project — ProjectContext container."""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "yaml" not in sys.modules:
    yaml_stub = types.ModuleType("yaml")
    yaml_stub.safe_load = lambda *_args, **_kwargs: {}
    sys.modules["yaml"] = yaml_stub

from core.project import ProjectContext, _detect_repository_root


def test_detect_repository_root_workdir(tmp_path: Path) -> None:
    """Если проект в _workdir/ — repository_root = _workdir/.."""
    workdir = tmp_path / "_workdir"
    project = workdir / "myproject"
    project.mkdir(parents=True)

    assert _detect_repository_root(project) == tmp_path


def test_detect_repository_root_other(tmp_path: Path) -> None:
    """Если проект НЕ в _workdir/ — repository_root = parent."""
    project = tmp_path / "myproject"
    project.mkdir()

    assert _detect_repository_root(project) == tmp_path


def test_from_project_root_creates_loader(tmp_path: Path) -> None:
    """from_project_root создаёт ProjectContext с ConfigLoader."""
    project = tmp_path / "myproject"
    project.mkdir()

    ctx = ProjectContext.from_project_root(project)

    assert ctx.project_root == project.resolve()
    assert ctx.repository_root == tmp_path.resolve()
    assert ctx.config_loader is not None
    assert ctx.rename_map == {}


def test_relative_to_root(tmp_path: Path) -> None:
    project = tmp_path / "myproject"
    project.mkdir()
    nested = project / "css" / "style.css"
    nested.parent.mkdir()
    nested.touch()

    ctx = ProjectContext.from_project_root(project)
    assert ctx.relative_to_root(nested) == "css/style.css"


def test_ensure_logs_dir_creates(tmp_path: Path) -> None:
    project = tmp_path / "_workdir" / "myproject"
    project.mkdir(parents=True)

    ctx = ProjectContext.from_project_root(project)
    logs = ctx.ensure_logs_dir()

    assert logs.exists()
    assert logs == tmp_path / "logs"


def test_ensure_logs_dir_uses_argument(tmp_path: Path) -> None:
    """Можно передать кастомный путь к логам."""
    project = tmp_path / "myproject"
    project.mkdir()
    custom_logs = tmp_path / "custom_logs"

    ctx = ProjectContext.from_project_root(project)
    logs = ctx.ensure_logs_dir(custom_logs)

    assert logs == custom_logs
    assert custom_logs.exists()


def test_update_rename_map_accumulates(tmp_path: Path) -> None:
    project = tmp_path / "myproject"
    project.mkdir()

    ctx = ProjectContext.from_project_root(project)
    ctx.update_rename_map({"a.html": "x.html"})
    ctx.update_rename_map({"b.css": "y.css"})

    assert ctx.rename_map == {"a.html": "x.html", "b.css": "y.css"}
