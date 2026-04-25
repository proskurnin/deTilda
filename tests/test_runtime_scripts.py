"""Tests for core.runtime_scripts — protect scripts needed by media blocks."""
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

from core.runtime_scripts import (
    CONDITIONALLY_REQUIRED_RUNTIME_SCRIPTS,
    filter_removable_scripts,
    project_needs_media_runtime,
)


def test_no_media_returns_false(tmp_path: Path) -> None:
    (tmp_path / "page.html").write_text("<html><body>plain text</body></html>")
    assert project_needs_media_runtime(tmp_path) is False


def test_no_html_files_returns_false(tmp_path: Path) -> None:
    (tmp_path / "data.txt").write_text("youtube.com")  # не HTML — не считается
    assert project_needs_media_runtime(tmp_path) is False


def test_youtube_link_triggers_media(tmp_path: Path) -> None:
    (tmp_path / "page.html").write_text(
        '<a href="https://youtube.com/watch?v=abc">video</a>'
    )
    assert project_needs_media_runtime(tmp_path) is True


def test_t_video_class_triggers_media(tmp_path: Path) -> None:
    (tmp_path / "page.html").write_text('<div class="t-video"></div>')
    assert project_needs_media_runtime(tmp_path) is True


def test_data_original_triggers_media(tmp_path: Path) -> None:
    (tmp_path / "page.html").write_text('<img data-original="bg.jpg" />')
    assert project_needs_media_runtime(tmp_path) is True


def test_filter_removes_all_when_no_media(tmp_path: Path) -> None:
    """Без медиа-маркеров все скрипты подлежат удалению."""
    (tmp_path / "page.html").write_text("<html><body>nothing</body></html>")

    scripts = ["tilda-events-1.0.min.js", "tilda-stat-1.0.min.js"]
    removable, preserved = filter_removable_scripts(scripts, tmp_path)

    assert removable == scripts
    assert preserved == []


def test_filter_protects_runtime_when_media_present(tmp_path: Path) -> None:
    """С медиа-маркерами runtime-скрипты сохраняются, остальные удаляются."""
    (tmp_path / "page.html").write_text('<div class="t-gallery"></div>')

    scripts = [
        "tilda-events-1.0.min.js",      # CONDITIONALLY_REQUIRED → сохранить
        "tilda-fallback-1.0.min.js",    # CONDITIONALLY_REQUIRED → сохранить
        "tilda-stat-1.0.min.js",        # → удалить
        "tilda-forms-1.0.min.js",       # → удалить
    ]
    removable, preserved = filter_removable_scripts(scripts, tmp_path)

    assert "tilda-events-1.0.min.js" in preserved
    assert "tilda-fallback-1.0.min.js" in preserved
    assert "tilda-stat-1.0.min.js" in removable
    assert "tilda-forms-1.0.min.js" in removable


def test_filter_handles_empty_input(tmp_path: Path) -> None:
    removable, preserved = filter_removable_scripts([], tmp_path)
    assert removable == []
    assert preserved == []


def test_filter_strips_whitespace_and_skips_empty(tmp_path: Path) -> None:
    """Пробелы триммятся, пустые строки игнорируются."""
    (tmp_path / "page.html").write_text("<html></html>")

    removable, _ = filter_removable_scripts(
        ["  tilda-stat.js  ", "", "   "], tmp_path
    )
    assert removable == ["tilda-stat.js"]


def test_aida_variants_also_protected(tmp_path: Path) -> None:
    """aida-* варианты (после переименования) тоже защищены."""
    assert "aida-events-1.0.min.js" in CONDITIONALLY_REQUIRED_RUNTIME_SCRIPTS
    assert "aida-fallback-1.0.min.js" in CONDITIONALLY_REQUIRED_RUNTIME_SCRIPTS

    (tmp_path / "page.html").write_text('<div class="t-slds"></div>')
    removable, preserved = filter_removable_scripts(
        ["aida-events-1.0.min.js"], tmp_path
    )
    assert preserved == ["aida-events-1.0.min.js"]
    assert removable == []
