"""Tests for core.api.process_archive — public programmatic entry point."""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.api import process_archive
from core.pipeline import PipelineStats

_HTML = "<html><head></head><body><div class='t-rec'>hi</div></body></html>"


@pytest.fixture()
def simple_zip(tmp_path: Path) -> Path:
    workdir = tmp_path / "_workdir"
    workdir.mkdir()
    for subdir in ("config", "resources"):
        src = ROOT / subdir
        if src.exists():
            (tmp_path / subdir).symlink_to(src)
    zip_path = workdir / "site.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("site/index.html", _HTML)
    return zip_path


def test_returns_pipeline_stats(simple_zip: Path, tmp_path: Path) -> None:
    stats = process_archive(simple_zip, logs_dir=tmp_path / "logs")
    assert isinstance(stats, PipelineStats)
    assert stats.exec_time > 0


def test_dry_run_flag_forwarded(simple_zip: Path, tmp_path: Path) -> None:
    """dry_run пробрасывается в DetildaPipeline — index.html не перезаписывается."""
    html_path = simple_zip.parent / "site" / "index.html"
    stats = process_archive(simple_zip, dry_run=True, logs_dir=tmp_path / "logs")
    assert isinstance(stats, PipelineStats)
    assert "t-rec" in html_path.read_text(encoding="utf-8")


def test_raises_on_missing_archive(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        process_archive(tmp_path / "nonexistent.zip")


def test_accepts_string_path(simple_zip: Path, tmp_path: Path) -> None:
    stats = process_archive(str(simple_zip), logs_dir=str(tmp_path / "logs"))
    assert isinstance(stats, PipelineStats)
