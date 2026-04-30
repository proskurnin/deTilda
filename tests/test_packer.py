"""Tests for core.packer.pack_result."""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.packer import pack_result


def test_returns_valid_zip(tmp_path: Path) -> None:
    """pack_result возвращает корректный ZIP."""
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    result = pack_result(tmp_path)
    assert zipfile.is_zipfile(io.BytesIO(result))


def test_zip_contains_all_files(tmp_path: Path) -> None:
    """Все файлы из папки попадают в ZIP с правильными путями."""
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    css = tmp_path / "css"
    css.mkdir()
    (css / "style.css").write_text("body{}", encoding="utf-8")

    result = pack_result(tmp_path)

    with zipfile.ZipFile(io.BytesIO(result)) as zf:
        names = zf.namelist()

    assert "index.html" in names
    assert "css/style.css" in names


def test_zip_content_matches_original(tmp_path: Path) -> None:
    """Содержимое файлов в ZIP совпадает с оригиналом."""
    content = "<html><body>test</body></html>"
    (tmp_path / "index.html").write_text(content, encoding="utf-8")

    result = pack_result(tmp_path)

    with zipfile.ZipFile(io.BytesIO(result)) as zf:
        assert zf.read("index.html").decode("utf-8") == content


def test_raises_on_missing_folder(tmp_path: Path) -> None:
    """FileNotFoundError если папка не существует."""
    with pytest.raises(FileNotFoundError):
        pack_result(tmp_path / "nonexistent")


def test_pipeline_stats_expose_project_root(tmp_path: Path) -> None:
    """PipelineStats.project_root заполняется после pipeline.run()."""
    import zipfile as zf_mod
    from core.api import process_archive

    workdir = tmp_path / "_workdir"
    workdir.mkdir()
    for subdir in ("config", "resources"):
        src = ROOT / subdir
        if src.exists():
            (tmp_path / subdir).symlink_to(src)

    zip_path = workdir / "site.zip"
    with zf_mod.ZipFile(zip_path, "w") as zf:
        zf.writestr("site/index.html", "<html></html>")

    stats = process_archive(zip_path, logs_dir=tmp_path / "logs")

    assert stats.project_root is not None
    assert stats.project_root.exists()
    assert (stats.project_root / "index.html").exists()

    # Упаковываем результат — должны получить валидный ZIP
    zip_bytes = pack_result(stats.project_root)
    assert zipfile.is_zipfile(io.BytesIO(zip_bytes))
