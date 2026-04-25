"""Tests for core.archive — ZIP extraction with two structure modes."""
from __future__ import annotations

import sys
import types
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "yaml" not in sys.modules:
    yaml_stub = types.ModuleType("yaml")
    yaml_stub.safe_load = lambda *_args, **_kwargs: {}
    sys.modules["yaml"] = yaml_stub

from core.archive import unpack_archive


def _make_zip(zip_path: Path, files: dict[str, str]) -> None:
    """Создаёт ZIP с заданным содержимым {путь: контент}."""
    with zipfile.ZipFile(zip_path, "w") as zf:
        for arcname, content in files.items():
            zf.writestr(arcname, content)


def test_unpack_returns_none_when_archive_missing(tmp_path: Path) -> None:
    result = unpack_archive(tmp_path / "nonexistent.zip")
    assert result is None


def test_unpack_returns_none_for_corrupt_zip(tmp_path: Path) -> None:
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip file")
    result = unpack_archive(bad)
    assert result is None


def test_unpack_single_root_folder(tmp_path: Path) -> None:
    """Стандартный экспорт Tilda: одна корневая папка внутри архива."""
    zip_path = tmp_path / "project12345.zip"
    _make_zip(zip_path, {
        "project12345/index.html": "<html></html>",
        "project12345/css/style.css": "body{}",
    })

    result = unpack_archive(zip_path)

    assert result == tmp_path / "project12345"
    assert (tmp_path / "project12345" / "index.html").exists()
    assert (tmp_path / "project12345" / "css" / "style.css").exists()


def test_unpack_multi_root_creates_wrapper_folder(tmp_path: Path) -> None:
    """Файлы в корне архива → распаковываются в папку по имени архива."""
    zip_path = tmp_path / "myarchive.zip"
    _make_zip(zip_path, {
        "index.html": "<html></html>",
        "css/style.css": "body{}",
    })

    result = unpack_archive(zip_path)

    assert result == tmp_path / "myarchive"
    assert (tmp_path / "myarchive" / "index.html").exists()
    assert (tmp_path / "myarchive" / "css" / "style.css").exists()
    # Временная папка удалилась
    assert not (tmp_path / "_detilda_extract_tmp").exists()


def test_unpack_replaces_existing_target(tmp_path: Path) -> None:
    """Если папка назначения существует — удаляется перед распаковкой."""
    zip_path = tmp_path / "project12345.zip"
    _make_zip(zip_path, {"project12345/new.html": "<h1>new</h1>"})

    # Создаём существующую папку с другим контентом
    existing = tmp_path / "project12345"
    existing.mkdir()
    (existing / "old.html").write_text("<h1>old</h1>")

    result = unpack_archive(zip_path)

    assert result == existing
    assert (existing / "new.html").exists()
    assert not (existing / "old.html").exists()  # старый файл удалён вместе с папкой
