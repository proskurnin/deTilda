"""Tests for core.refs — main update_all_refs_in_project flow."""
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

from core.refs import update_all_refs_in_project
from core.schemas import ImagesConfig, PatternsConfig


class _FakeLoader:
    """Минимальный конфиг для тестов refs.py."""

    def __init__(
        self,
        text_extensions=None,
        replace_rules=None,
        ignore_prefixes=None,
        link_rel_values=None,
        replace_patterns=None,
        comment_patterns=None,
    ):
        self._patterns = PatternsConfig.model_validate({
            "links": [
                r'(?P<attr>href|src|action)\s*=\s*"(?P<link>[^"]+)"',
            ],
            "text_extensions": text_extensions or [".html"],
            "replace_rules": replace_rules or [],
            "ignore_prefixes": ignore_prefixes or ["http://", "https://", "//", "#"],
            "htaccess_patterns": {
                "rewrite_rule": "(?im)^[ \\t]*RewriteRule[ \\t]+\\^/?([a-z0-9\\-_/]+)\\??\\$?[ \\t]+([^ \\t]+)",
                "redirect": "(?im)^[ \\t]*Redirect[ \\t]+(/[^ \\t]+)[ \\t]+([^ \\t]+)",
                "remove_unresolved_routes": False,
            },
        })
        self._images = ImagesConfig.model_validate({
            "comment_out_link_tags": {"rel_values": link_rel_values or []},
            "replace_links_with_1px": {"patterns": replace_patterns or []},
            "comment_out_links": {"patterns": comment_patterns or []},
        })

    def patterns(self) -> PatternsConfig:
        return self._patterns

    def images(self) -> ImagesConfig:
        return self._images


def test_applies_rename_map_to_html_links(tmp_path: Path) -> None:
    """Карта переименований применяется к ссылкам в HTML."""
    page = tmp_path / "index.html"
    page.write_text(
        '<html><body><a href="til-page.html">link</a></body></html>',
        encoding="utf-8",
    )
    (tmp_path / "ai-page.html").write_text("ok")

    rename_map = {"til-page.html": "ai-page.html"}
    fixed, broken = update_all_refs_in_project(tmp_path, rename_map, _FakeLoader())

    text = page.read_text(encoding="utf-8")
    assert "ai-page.html" in text
    assert "til-page.html" not in text
    assert fixed >= 1
    assert broken == 0


def test_applies_replace_rules(tmp_path: Path) -> None:
    """replace_rules применяются ко всему тексту HTML файла."""
    page = tmp_path / "index.html"
    page.write_text(
        '<div class="t-block">content</div>',
        encoding="utf-8",
    )

    loader = _FakeLoader(replace_rules=[{"pattern": r"\bt-", "replacement": "ai-"}])
    update_all_refs_in_project(tmp_path, {}, loader)

    text = page.read_text(encoding="utf-8")
    assert 'class="ai-block"' in text


def test_skips_external_urls(tmp_path: Path) -> None:
    """Внешние URL (http/https) не трогаются."""
    page = tmp_path / "index.html"
    page.write_text(
        '<a href="https://external.com/page">link</a>',
        encoding="utf-8",
    )

    update_all_refs_in_project(tmp_path, {}, _FakeLoader())

    text = page.read_text(encoding="utf-8")
    assert "https://external.com/page" in text


def test_marks_broken_relative_links(tmp_path: Path) -> None:
    """Относительные ссылки на несуществующие файлы помечаются как битые."""
    page = tmp_path / "index.html"
    page.write_text(
        '<img src="missing.png" alt="x" />',
        encoding="utf-8",
    )

    fixed, broken = update_all_refs_in_project(tmp_path, {}, _FakeLoader())

    assert broken >= 1


def test_existing_relative_link_not_broken(tmp_path: Path) -> None:
    """Ссылки на существующие файлы не помечаются как битые."""
    page = tmp_path / "index.html"
    page.write_text('<img src="image.png" />', encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"fake")

    fixed, broken = update_all_refs_in_project(tmp_path, {}, _FakeLoader())

    assert broken == 0


def test_missing_js_src_is_not_rewritten_to_hash(tmp_path: Path) -> None:
    """Missing JS src stays intact so script_cleaner can remove known Tilda scripts."""
    page = tmp_path / "index.html"
    page.write_text(
        '<html><head><script src="js/aida-forms-1.0.min.js"></script></head></html>',
        encoding="utf-8",
    )

    _fixed, broken = update_all_refs_in_project(tmp_path, {}, _FakeLoader())

    text = page.read_text(encoding="utf-8")
    assert broken >= 1
    assert 'src="js/aida-forms-1.0.min.js"' in text
    assert 'src="#"' not in text


def test_removes_empty_script_src_hash_tags(tmp_path: Path) -> None:
    """Invalid <script src="#"></script> tags from older runs are removed."""
    page = tmp_path / "index.html"
    page.write_text(
        '<html><head><script src="#"></script></head><body>ok</body></html>',
        encoding="utf-8",
    )

    fixed, _broken = update_all_refs_in_project(tmp_path, {}, _FakeLoader())

    text = page.read_text(encoding="utf-8")
    assert fixed >= 1
    assert '<script src="#"></script>' not in text
    assert "<head></head>" in text


def test_preserves_js_cache_busting_query(tmp_path: Path) -> None:
    """Page-specific Tilda runtime JS keeps ?t=... to avoid stale browser cache."""
    page = tmp_path / "index.html"
    page.write_text(
        '<script src="js/aida-blocks-page27969817.min.js?t=1655879501"></script>',
        encoding="utf-8",
    )
    (tmp_path / "js").mkdir()
    (tmp_path / "js" / "aida-blocks-page27969817.min.js").write_text("", encoding="utf-8")

    _fixed, broken = update_all_refs_in_project(tmp_path, {}, _FakeLoader())

    text = page.read_text(encoding="utf-8")
    assert broken == 0
    assert 'src="js/aida-blocks-page27969817.min.js?t=1655879501"' in text


def test_absolute_root_link_converted_to_relative_from_root_page(tmp_path: Path) -> None:
    """`/favicon.ico` в корневой странице → `favicon.ico` (для file:// preview)."""
    page = tmp_path / "index.html"
    page.write_text(
        '<link rel="shortcut icon" href="/favicon.ico" />',
        encoding="utf-8",
    )
    (tmp_path / "favicon.ico").write_bytes(b"\x00")

    fixed, broken = update_all_refs_in_project(tmp_path, {}, _FakeLoader())

    text = page.read_text(encoding="utf-8")
    assert 'href="favicon.ico"' in text
    assert 'href="/favicon.ico"' not in text
    assert broken == 0


def test_absolute_root_link_converted_to_relative_from_subdir_page(tmp_path: Path) -> None:
    """`/favicon.ico` в `subdir/page.html` → `../favicon.ico`."""
    (tmp_path / "subdir").mkdir()
    page = tmp_path / "subdir" / "page.html"
    page.write_text('<img src="/favicon.ico" />', encoding="utf-8")
    (tmp_path / "favicon.ico").write_bytes(b"\x00")

    update_all_refs_in_project(tmp_path, {}, _FakeLoader())

    text = page.read_text(encoding="utf-8")
    assert 'src="../favicon.ico"' in text


def test_absolute_root_link_via_rename_map_uses_relative_path(tmp_path: Path) -> None:
    """Абсолютная ссылка через rename_map тоже становится относительной."""
    (tmp_path / "subdir").mkdir()
    page = tmp_path / "subdir" / "page.html"
    page.write_text('<a href="/til-old.html">x</a>', encoding="utf-8")
    (tmp_path / "ai-new.html").write_text("ok")

    rename_map = {"til-old.html": "ai-new.html"}
    update_all_refs_in_project(tmp_path, rename_map, _FakeLoader())

    text = page.read_text(encoding="utf-8")
    assert 'href="../ai-new.html"' in text


def test_replace_with_1px_images(tmp_path: Path) -> None:
    """replace_links_with_1px заменяет ссылки на 1px placeholder."""
    page = tmp_path / "index.html"
    page.write_text('<img src="tildacopy.png" />', encoding="utf-8")
    # 1px.png должен существовать — иначе broken-handler пометит как битую
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "1px.png").write_bytes(b"fake-png")

    loader = _FakeLoader(replace_patterns=["tildacopy.png"])
    update_all_refs_in_project(tmp_path, {}, loader)

    text = page.read_text(encoding="utf-8")
    assert "tildacopy.png" not in text
    assert "1px.png" in text


def test_comment_out_link_tags(tmp_path: Path) -> None:
    """<link rel="icon"> комментируется."""
    page = tmp_path / "index.html"
    page.write_text(
        '<head><link rel="icon" href="/favicon.ico" /></head>',
        encoding="utf-8",
    )

    loader = _FakeLoader(link_rel_values=["icon"])
    update_all_refs_in_project(tmp_path, {}, loader)

    text = page.read_text(encoding="utf-8")
    assert "<!-- <link" in text


def test_processes_multiple_extensions(tmp_path: Path) -> None:
    """text_extensions определяет какие файлы обрабатываются."""
    (tmp_path / "page.html").write_text('<a href="til.css">link</a>')
    (tmp_path / "style.css").write_text('background: url("til.png");')
    (tmp_path / "data.json").write_text('{"file":"til.html"}')

    rename_map = {"til.css": "ai.css", "til.png": "ai.png", "til.html": "ai.html"}

    loader = _FakeLoader(text_extensions=[".html", ".css"])
    update_all_refs_in_project(tmp_path, rename_map, loader)

    assert "ai.css" in (tmp_path / "page.html").read_text()
    assert "ai.png" in (tmp_path / "style.css").read_text()
    # JSON не в списке расширений — не тронут
    assert "til.html" in (tmp_path / "data.json").read_text()


def test_anchors_skipped(tmp_path: Path) -> None:
    """Внутренние якори (#section) не трогаются."""
    page = tmp_path / "index.html"
    page.write_text('<a href="#section">link</a>', encoding="utf-8")

    update_all_refs_in_project(tmp_path, {}, _FakeLoader())

    text = page.read_text(encoding="utf-8")
    assert 'href="#section"' in text


def test_returns_fixed_and_broken_counts(tmp_path: Path) -> None:
    """Возвращает (fixed, broken) tuple."""
    (tmp_path / "page.html").write_text('<a href="til.html">x</a>')
    (tmp_path / "ai.html").write_text("")

    fixed, broken = update_all_refs_in_project(
        tmp_path, {"til.html": "ai.html"}, _FakeLoader()
    )

    assert isinstance(fixed, int)
    assert isinstance(broken, int)
    assert fixed >= 1
