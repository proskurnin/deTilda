"""Tests for core.page404 — normalize 404.html cleanup."""
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

from core.page404 import update_404_page


def test_returns_false_when_page_missing(tmp_path: Path) -> None:
    assert update_404_page(tmp_path) is False


def test_normalizes_title_when_wrong(tmp_path: Path) -> None:
    page = tmp_path / "404.html"
    page.write_text("<html><head><title>Page not found - Tilda</title></head><body></body></html>")
    assert update_404_page(tmp_path) is True
    text = page.read_text()
    assert "<title>Page 404, oooops...</title>" in text


def test_inserts_title_when_absent(tmp_path: Path) -> None:
    page = tmp_path / "404.html"
    page.write_text("<html><head><meta charset='utf-8'></head><body></body></html>")
    assert update_404_page(tmp_path) is True
    text = page.read_text()
    assert "<title>Page 404, oooops...</title>" in text


def test_replaces_tilda_link_with_message(tmp_path: Path) -> None:
    """Паттерн ищет ссылки с href, заканчивающимся на .cc — стандартный формат Tilda."""
    page = tmp_path / "404.html"
    page.write_text(
        '<html><body><a href="https://tilda.cc">Made on Tilda</a></body></html>'
    )
    assert update_404_page(tmp_path) is True
    text = page.read_text()
    assert "tilda.cc" not in text
    assert "<h1>404</h1>" in text


def test_inserts_message_when_no_tilda_link(tmp_path: Path) -> None:
    page = tmp_path / "404.html"
    page.write_text("<html><body><div>Some content</div></body></html>")
    assert update_404_page(tmp_path) is True
    text = page.read_text()
    assert "<h1>404</h1>" in text
    assert "Page not found, oooops..." in text


def test_removes_all_script_tags(tmp_path: Path) -> None:
    page = tmp_path / "404.html"
    page.write_text(
        "<html><body>"
        "<script>tilda_stat();</script>"
        "<script src='/js/tilda.js'></script>"
        "<p>Hello</p>"
        "</body></html>"
    )
    assert update_404_page(tmp_path) is True
    text = page.read_text()
    assert "<script" not in text
    assert "tilda_stat" not in text
    assert "<p>Hello</p>" in text


def test_returns_false_when_already_clean(tmp_path: Path) -> None:
    page = tmp_path / "404.html"
    page.write_text(
        "<html><head><title>Page 404, oooops...</title></head>"
        "<body><h1>404</h1><p>Page not found, oooops...</p></body></html>"
    )
    assert update_404_page(tmp_path) is False
