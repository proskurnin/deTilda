"""Tests for core.utils — file I/O and path helpers."""
from __future__ import annotations

import json
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "yaml" not in sys.modules:
    yaml_stub = types.ModuleType("yaml")
    yaml_stub.safe_load = lambda *_args, **_kwargs: {}
    sys.modules["yaml"] = yaml_stub

from core import utils


def test_safe_read_returns_content(tmp_path: Path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("hello", encoding="utf-8")
    assert utils.safe_read(f) == "hello"


def test_safe_read_handles_bom(tmp_path: Path) -> None:
    """Файлы с BOM-маркером не вызывают UnicodeDecodeError."""
    f = tmp_path / "bom.txt"
    f.write_bytes(b"\xef\xbb\xbfhello")
    result = utils.safe_read(f)
    # BOM может остаться (﻿) или быть удалён — главное не падать
    assert result.endswith("hello")


def test_safe_read_raises_when_missing(tmp_path: Path) -> None:
    try:
        utils.safe_read(tmp_path / "missing.txt")
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError:
        pass


def test_safe_write_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "c.txt"
    utils.safe_write(target, "content")
    assert target.read_text(encoding="utf-8") == "content"


def test_safe_write_uses_unix_newlines(tmp_path: Path) -> None:
    target = tmp_path / "x.txt"
    utils.safe_write(target, "line1\nline2\n")
    assert target.read_bytes() == b"line1\nline2\n"


def test_safe_copy_creates_destination_dir(tmp_path: Path) -> None:
    src = tmp_path / "source.txt"
    src.write_text("data")
    dst = tmp_path / "nested" / "dest.txt"

    utils.safe_copy(src, dst)
    assert dst.read_text() == "data"


def test_safe_delete_removes_existing_file(tmp_path: Path) -> None:
    f = tmp_path / "f.txt"
    f.write_text("x")
    utils.safe_delete(f)
    assert not f.exists()


def test_safe_delete_silent_when_missing(tmp_path: Path) -> None:
    """Не падает если файла нет."""
    utils.safe_delete(tmp_path / "missing.txt")  # не должно быть исключения


def test_relpath_returns_relative(tmp_path: Path) -> None:
    base = tmp_path
    target = tmp_path / "sub" / "file.txt"
    target.parent.mkdir()
    target.touch()
    assert utils.relpath(target, base) == "sub/file.txt"


def test_relpath_returns_filename_when_outside_base(tmp_path: Path) -> None:
    """Если path вне base — возвращается только имя файла."""
    target = tmp_path / "file.txt"
    target.touch()
    other = tmp_path.parent / "other_dir"  # другая директория
    result = utils.relpath(target, other)
    assert result == "file.txt"


def test_ensure_dir_creates(tmp_path: Path) -> None:
    new = tmp_path / "new" / "deep"
    result = utils.ensure_dir(new)
    assert new.exists()
    assert result == new


def test_ensure_dir_idempotent(tmp_path: Path) -> None:
    """Не падает если папка уже существует."""
    utils.ensure_dir(tmp_path)
    utils.ensure_dir(tmp_path)


def test_list_files_recursive_finds_all(tmp_path: Path) -> None:
    (tmp_path / "a.html").touch()
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.css").touch()
    (tmp_path / "sub" / "c.js").touch()

    files = utils.list_files_recursive(tmp_path)
    names = sorted(f.name for f in files)
    assert names == ["a.html", "b.css", "c.js"]


def test_list_files_recursive_filters_extensions(tmp_path: Path) -> None:
    (tmp_path / "a.html").touch()
    (tmp_path / "b.css").touch()
    (tmp_path / "c.js").touch()

    files = utils.list_files_recursive(tmp_path, extensions=(".html", ".css"))
    names = sorted(f.name for f in files)
    assert names == ["a.html", "b.css"]


def test_list_files_recursive_case_insensitive_extensions(tmp_path: Path) -> None:
    (tmp_path / "a.HTML").touch()
    (tmp_path / "b.html").touch()

    files = utils.list_files_recursive(tmp_path, extensions=(".html",))
    assert len(files) == 2


def test_get_elapsed_time_seconds() -> None:
    start = time.time() - 5.5
    result = utils.get_elapsed_time(start)
    assert result.endswith("s")
    assert "5." in result  # около 5 секунд


def test_get_elapsed_time_minutes() -> None:
    start = time.time() - 125  # 2 минуты 5 секунд
    result = utils.get_elapsed_time(start)
    assert "m" in result
    assert "2m" in result


def test_load_manifest_returns_dict(tmp_path: Path) -> None:
    """load_manifest читает существующий manifest.json в корне репо."""
    manifest = utils.load_manifest()
    assert isinstance(manifest, dict)
    # В реальном manifest.json есть version и paths
    assert "version" in manifest
