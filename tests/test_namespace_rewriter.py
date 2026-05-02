from __future__ import annotations

from pathlib import Path

from core.namespace_rewriter import rewrite_project_namespace, rewrite_text, scan_leftovers


def test_rewrites_form_html_js_and_inline_function_names(tmp_path: Path) -> None:
    page = tmp_path / "page.html"
    page.write_text(
        """
        <html><body class="t-body">
          <div class="t-records">
            <form class="t-form" data-tilda-formskey="abc">
              <input class="t-input t-input__vis-ph">
              <button class="t-submit">Send</button>
            </form>
          </div>
          <script>
            t_onReady(function () {
              t_onFuncLoad('t396_init', function () { t396_init('123'); });
              t_zeroForms__init('123');
            });
          </script>
        </body></html>
        """,
        encoding="utf-8",
    )
    script = tmp_path / "js" / "tilda-zero-forms-1.0.min.js"
    script.parent.mkdir()
    script.write_text(
        "function t_zeroForms__init(id){"
        "document.querySelector('.t-form [data-tilda-formskey] .t-input');"
        "}",
        encoding="utf-8",
    )

    result = rewrite_project_namespace(tmp_path)

    assert result.critical_leftovers_total == 0
    html = page.read_text(encoding="utf-8")
    assert "ai-body" in html
    assert "ai-records" in html
    assert "ai-form" in html
    assert "ai-input" in html
    assert "data-aida-formskey" in html
    assert "ai_onReady" in html
    assert "'ai396_init'" in html
    assert "ai396_init(" in html
    assert "ai_zeroForms__init" in html

    renamed_script = tmp_path / "js" / "aida-zero-forms-1.0.min.js"
    assert renamed_script.exists()
    js = renamed_script.read_text(encoding="utf-8")
    assert "function ai_zeroForms__init" in js
    assert ".ai-form [data-aida-formskey] .ai-input" in js
    assert "deTilda zero-forms namespace bridge" in js
    assert "w[legacy]=w[ai]" in js
    assert "t_zeroForms__init" not in js


def test_rewrite_js_keeps_arithmetic_t_minus_identifier() -> None:
    text = (
        "var x='t-form';"
        "function t396_init(id){return id}"
        "function f(t){return o-(t-this._previousLoopTime)}"
        "t_onFuncLoad('t396_init',function(){t396_init('1')});"
    )

    rewritten, count = rewrite_text(text, ".js")

    assert count >= 5
    assert "'ai-form'" in rewritten
    assert "function ai396_init" in rewritten
    assert "ai_onFuncLoad('ai396_init'" in rewritten
    assert "ai396_init('1')" in rewritten
    assert "(t-this._previousLoopTime)" in rewritten
    assert "ai-this" not in rewritten


def test_does_not_rewrite_msapplication_tile_meta(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    page.write_text(
        '<meta name="msapplication-TileColor" content="#fff">'
        '<meta name="msapplication-TileImage" content="tile.png">'
        '<div class="t-title">Tilda</div>',
        encoding="utf-8",
    )

    rewrite_project_namespace(tmp_path)

    text = page.read_text(encoding="utf-8")
    assert "msapplication-TileColor" in text
    assert "msapplication-TileImage" in text
    assert "ai-title" in text
    assert "Aida" in text


def test_scan_leftovers_reports_critical_patterns(tmp_path: Path) -> None:
    page = tmp_path / "bad.html"
    page.write_text(
        '<div class="t-form" data-tilda-formskey="x"></div>'
        "<script>t_zeroForms__init('1')</script>",
        encoding="utf-8",
    )

    critical, _warnings = scan_leftovers(tmp_path)

    assert critical["data-tilda-"] == 1
    assert critical["class contains t-"] == 1
    assert critical["t_zeroForms__init"] == 1


def test_scan_leftovers_reports_external_tilda_urls_as_warnings(tmp_path: Path) -> None:
    page = tmp_path / "cdn.html"
    page.write_text(
        '<script src="https://static.tildacdn.com/js/tilda-extra.js"></script>',
        encoding="utf-8",
    )

    critical, warnings = scan_leftovers(tmp_path)

    assert critical == {}
    assert warnings["external tilda URL"] == 1


def test_renames_downloaded_tilda_file_and_updates_references(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    page.write_text('<script src="js/tilda-extra.js"></script>', encoding="utf-8")
    script = tmp_path / "js" / "tilda-extra.js"
    script.parent.mkdir()
    script.write_text("window.Tilda={};", encoding="utf-8")

    result = rewrite_project_namespace(tmp_path)

    assert result.renamed_paths == 1
    assert not script.exists()
    assert (tmp_path / "js" / "aida-extra.js").exists()
    assert 'src="js/aida-extra.js"' in page.read_text(encoding="utf-8")
