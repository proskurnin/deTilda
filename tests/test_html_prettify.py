from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core import html_prettify


@dataclass
class _Stats:
    warnings: int = 0
    errors: int = 0
    formatted_html_files: int = 0
    html_prettify_skipped: bool = False


@dataclass
class _Context:
    project_root: Path


def test_html_prettify_skips_once_without_lxml_or_bs4(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "index.html").write_text("<html><body><h1>x</h1></body></html>", encoding="utf-8")
    (tmp_path / "about.html").write_text("<html><body><h1>y</h1></body></html>", encoding="utf-8")

    warnings: list[str] = []
    errors: list[str] = []
    infos: list[str] = []

    monkeypatch.setattr(html_prettify, "etree", None)
    monkeypatch.setattr(html_prettify, "html", None)
    monkeypatch.setattr(html_prettify, "BeautifulSoup", None)
    monkeypatch.setattr(html_prettify.logger, "warn", warnings.append)
    monkeypatch.setattr(html_prettify.logger, "err", errors.append)
    monkeypatch.setattr(html_prettify.logger, "info", infos.append)

    stats = _Stats()
    formatted = html_prettify.run(_Context(project_root=tmp_path), stats=stats)

    assert formatted == 0
    assert stats.warnings == 1
    assert stats.errors == 0
    assert stats.html_prettify_skipped is True
    assert len(warnings) == 1
    assert "skipped: lxml not installed" in warnings[0]
    assert len(errors) == 0
    assert not any("▶️ Начало работы" in line for line in infos)
