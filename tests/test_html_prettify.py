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


def test_html_output_becomes_multiline_and_readable(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    page.write_text("<html><head><meta charset='utf-8'><title>X</title></head><body><main><section><h1>Hi</h1></section></main></body></html>", encoding="utf-8")

    formatted = html_prettify.run(_Context(project_root=tmp_path), stats=_Stats())

    output = page.read_text(encoding="utf-8")
    assert formatted == 1
    assert "\n  <head>\n" in output
    assert "\n  <body>\n" in output
    assert output.count("\n") > 6


def test_indentation_is_stable(tmp_path: Path) -> None:
    page = tmp_path / "nested.htm"
    page.write_text("<html><body><main><section><div><p>Text</p></div></section></main></body></html>", encoding="utf-8")

    html_prettify.run(_Context(project_root=tmp_path), stats=_Stats())

    lines = page.read_text(encoding="utf-8").splitlines()
    assert "  <body>" in lines
    assert "    <main>" in lines
    assert "      <section>" in lines
    assert "        <div>" in lines


def test_repeated_formatting_is_idempotent(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    page.write_text("<html><body><div><span>Ok</span></div></body></html>", encoding="utf-8")

    html_prettify.run(_Context(project_root=tmp_path), stats=_Stats())
    first = page.read_text(encoding="utf-8")

    html_prettify.run(_Context(project_root=tmp_path), stats=_Stats())
    second = page.read_text(encoding="utf-8")

    assert first == second


def test_inline_script_content_is_preserved(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    script = "<script>window.__x = '<tag>' + \" & \";\nconsole.log(window.__x);</script>"
    page.write_text(f"<html><body>{script}</body></html>", encoding="utf-8")

    html_prettify.run(_Context(project_root=tmp_path), stats=_Stats())

    output = page.read_text(encoding="utf-8")
    assert script in output


def test_inline_style_content_is_preserved(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    style = "<style>.x::before{content:'Привет &copy;';display:block;}</style>"
    page.write_text(f"<html><head>{style}</head><body></body></html>", encoding="utf-8")

    html_prettify.run(_Context(project_root=tmp_path), stats=_Stats())

    output = page.read_text(encoding="utf-8")
    assert style in output


def test_attributes_and_data_attributes_are_preserved(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    tag = '<div id="a" class="b" data-track="hero" data-value="42"></div>'
    page.write_text(f"<html><body>{tag}</body></html>", encoding="utf-8")

    html_prettify.run(_Context(project_root=tmp_path), stats=_Stats())

    output = page.read_text(encoding="utf-8")
    assert "id=\"a\"" in output
    assert "data-track=\"hero\"" in output
    assert "data-value=\"42\"" in output


def test_comments_are_preserved(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    comment = "<!-- analytics keep -->"
    page.write_text(f"<html><body>{comment}<div>ok</div></body></html>", encoding="utf-8")

    html_prettify.run(_Context(project_root=tmp_path), stats=_Stats())

    output = page.read_text(encoding="utf-8")
    assert comment in output


def test_unicode_and_entities_are_preserved(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    page.write_text("<html><body><p>Привет, мир &amp; тест &#169;</p></body></html>", encoding="utf-8")

    html_prettify.run(_Context(project_root=tmp_path), stats=_Stats())

    output = page.read_text(encoding="utf-8")
    assert "Привет, мир" in output
    assert "&amp;" in output
    assert "&#169;" in output


def test_result_html_remains_parseable(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    page.write_text("<html><body><main><section><h1>X</h1></section></main></body></html>", encoding="utf-8")

    html_prettify.run(_Context(project_root=tmp_path), stats=_Stats())

    from html.parser import HTMLParser

    class _Collector(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.seen_h1 = False
            self.h1_text = ""

        def handle_starttag(self, tag, attrs):
            if tag == "h1":
                self.seen_h1 = True

        def handle_endtag(self, tag):
            if tag == "h1":
                self.seen_h1 = False

        def handle_data(self, data):
            if self.seen_h1:
                self.h1_text += data

    parser = _Collector()
    parser.feed(page.read_text(encoding="utf-8"))
    assert parser.h1_text.strip() == "X"


def test_functional_markup_semantics_not_altered(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    source = (
        "<html><body>"
        "<form action='/send' method='post'><input name='name'><button type='submit'>Go</button></form>"
        "<a href='#popup:open'>Открыть</a>"
        "</body></html>"
    )
    page.write_text(source, encoding="utf-8")

    html_prettify.run(_Context(project_root=tmp_path), stats=_Stats())

    output = page.read_text(encoding="utf-8")
    assert "<form action='/send' method='post'>" in output
    assert "<input name='name'>" in output
    assert "<button type='submit'>Go</button>" in output
    assert "<a href='#popup:open'>Открыть</a>" in output


def test_all_html_and_htm_files_are_formatted_recursively(tmp_path: Path) -> None:
    nested = tmp_path / "pages"
    nested.mkdir()
    a = tmp_path / "index.html"
    b = nested / "about.htm"
    a.write_text("<html><body><div>a</div></body></html>", encoding="utf-8")
    b.write_text("<html><body><div>b</div></body></html>", encoding="utf-8")

    stats = _Stats()
    formatted = html_prettify.run(_Context(project_root=tmp_path), stats=stats)

    assert formatted == 2
    assert stats.formatted_html_files == 2
    assert "\n" in a.read_text(encoding="utf-8")
    assert "\n" in b.read_text(encoding="utf-8")
