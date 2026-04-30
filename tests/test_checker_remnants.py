"""Tests for core.checker.check_tilda_remnants — find and fix tilda links."""
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

from core import downloader
from core.checker import TildaRemnantsResult, check_tilda_remnants
from core.schemas import PatternsConfig, ServiceFilesConfig


_DEFAULT_REPLACE = [{"pattern": r"(?i)\btil", "replacement": "ai"}]


class _FakeLoader:
    def __init__(self, replace_rules=None, download_rules=None):
        # Используем `is None` чтобы можно было явно передать [] (никаких правил)
        rules = _DEFAULT_REPLACE if replace_rules is None else replace_rules
        self._patterns = PatternsConfig.model_validate({
            "links": [
                r'(?P<attr>href|src|action)\s*=\s*"(?P<link>[^"]+)"',
            ],
            "text_extensions": [".html"],
            "replace_rules": rules,
        })
        self._service = ServiceFilesConfig.model_validate({
            "remote_assets": {
                "rules": download_rules or [],
            },
        })

    def patterns(self) -> PatternsConfig:
        return self._patterns

    def service_files(self) -> ServiceFilesConfig:
        return self._service


def test_returns_zero_when_no_tilda(tmp_path: Path) -> None:
    """Если 'tilda' нигде нет — total_occurrences = 0."""
    (tmp_path / "page.html").write_text(
        '<a href="page.html">link</a>',
        encoding="utf-8",
    )

    result = check_tilda_remnants(tmp_path, _FakeLoader())
    assert isinstance(result, TildaRemnantsResult)
    assert result.total_occurrences == 0
    assert result.files_with_remnants == 0


def test_fixes_local_path_via_replace_rules(tmp_path: Path) -> None:
    """Локальные пути с 'tilda' исправляются через replace_rules (til→ai)."""
    page = tmp_path / "page.html"
    page.write_text('<a href="tilda-page.html">x</a>', encoding="utf-8")

    result = check_tilda_remnants(tmp_path, _FakeLoader())

    text = page.read_text(encoding="utf-8")
    assert "tilda-page.html" not in text
    assert "aida-page.html" in text
    # Исправлено — total_occurrences = 0
    assert result.total_occurrences == 0


def test_unfixable_local_path_increments_counter(tmp_path: Path) -> None:
    """Если replace_rules не помогли — увеличивается total_occurrences."""
    page = tmp_path / "page.html"
    page.write_text('<a href="tildaspecial">x</a>', encoding="utf-8")

    # replace_rules не покрывает 'tildaspecial' (нет паттерна на til-)
    loader = _FakeLoader(replace_rules=[
        {"pattern": r"completely-different", "replacement": "x"},
    ])
    result = check_tilda_remnants(tmp_path, loader)

    text = page.read_text(encoding="utf-8")
    assert "tildaspecial" in text  # не изменилось
    assert result.total_occurrences == 1
    assert result.files_with_remnants == 1


def test_absolute_url_downloads_locally(tmp_path: Path, monkeypatch) -> None:
    """Абсолютный URL с 'tilda' скачивается локально и заменяется на относительный."""
    page = tmp_path / "page.html"
    page.write_text(
        '<img src="https://tildacdn.com/path/image.png" />',
        encoding="utf-8",
    )

    # Мокаем скачивание
    monkeypatch.setattr(
        downloader, "fetch_bytes", lambda _url, **_kw: (b"png-data", False)
    )

    loader = _FakeLoader(download_rules=[
        {"folder": "images", "extensions": [".png"]},
    ])
    result = check_tilda_remnants(tmp_path, loader)

    text = page.read_text(encoding="utf-8")
    # URL заменён на относительный путь
    assert "tildacdn.com" not in text
    assert "image.png" in text
    # Файл сохранён
    assert (tmp_path / "images" / "image.png").exists()


def test_absolute_url_fallback_to_replace_rules(tmp_path: Path, monkeypatch) -> None:
    """Если скачивание не удалось — применяются replace_rules."""
    page = tmp_path / "page.html"
    page.write_text(
        '<a href="https://tilda.cc/about">link</a>',
        encoding="utf-8",
    )

    # Без download_rules → download_to_project вернёт None
    loader = _FakeLoader(download_rules=[])
    result = check_tilda_remnants(tmp_path, loader)

    text = page.read_text(encoding="utf-8")
    # replace_rule til→ai применён
    assert "tilda.cc" not in text
    assert "aida.cc" in text


def test_counts_files_separately(tmp_path: Path) -> None:
    """files_with_remnants — количество файлов с неисправленными остатками."""
    (tmp_path / "page1.html").write_text('<a href="tildaspecial1">x</a>', encoding="utf-8")
    (tmp_path / "page2.html").write_text('<a href="tildaspecial2">x</a>', encoding="utf-8")
    (tmp_path / "clean.html").write_text('<a href="ok.html">x</a>', encoding="utf-8")

    loader = _FakeLoader(replace_rules=[])  # ничего не заменит
    result = check_tilda_remnants(tmp_path, loader)

    assert result.files_with_remnants == 2
    assert result.total_occurrences == 2


def test_case_insensitive_tilda_match(tmp_path: Path) -> None:
    """Поиск 'tilda' нечувствителен к регистру."""
    page = tmp_path / "page.html"
    page.write_text('<a href="TILDA-x">x</a>', encoding="utf-8")

    result = check_tilda_remnants(tmp_path, _FakeLoader())

    text = page.read_text(encoding="utf-8")
    assert "TILDA" not in text
    assert "ai" in text.lower()


def test_tilda_filename_detected(tmp_path: Path) -> None:
    """Файл с 'tilda' в имени попадает в tilda_filenames."""
    (tmp_path / "page.html").write_text("<p>ok</p>", encoding="utf-8")
    (tmp_path / "tildasite.css").write_text("body{}", encoding="utf-8")

    result = check_tilda_remnants(tmp_path, _FakeLoader())

    assert len(result.tilda_filenames) == 1
    assert "tildasite.css" in result.tilda_filenames[0]
    # Содержимое не затронуто — это сканер имён, не ссылок
    assert result.total_occurrences == 0


def test_no_tilda_filename_when_all_renamed(tmp_path: Path) -> None:
    """Если все файлы переименованы (ai-prefix) — tilda_filenames пуст."""
    (tmp_path / "aidasite.css").write_text("body{}", encoding="utf-8")
    (tmp_path / "index.html").write_text("<p>ok</p>", encoding="utf-8")

    result = check_tilda_remnants(tmp_path, _FakeLoader())

    assert result.tilda_filenames == []


def test_tilda_filename_case_insensitive(tmp_path: Path) -> None:
    """Поиск имён нечувствителен к регистру."""
    (tmp_path / "TILDASITE.CSS").write_text("body{}", encoding="utf-8")

    result = check_tilda_remnants(tmp_path, _FakeLoader())

    assert len(result.tilda_filenames) == 1
