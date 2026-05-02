from __future__ import annotations

from pathlib import Path

from core.checker import check_forms_integration


def test_forms_check_warns_when_handler_missing(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    page.write_text("<html><body><form></form></body></html>", encoding="utf-8")

    result = check_forms_integration(tmp_path)

    assert result.forms_found == 1
    assert result.forms_hooked == 0
    assert result.warnings == 1


def test_forms_check_counts_hooked_forms(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    page.write_text(
        '<html><body><form></form><script src="js/form-handler.js"></script></body></html>',
        encoding="utf-8",
    )

    result = check_forms_integration(tmp_path)

    assert result.forms_found == 1
    assert result.forms_hooked == 1
    assert result.warnings == 0


def test_forms_check_warns_when_zero_forms_runtime_is_stale(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    page.write_text(
        '<html><body><div class="tn-atom__form"></div>'
        '<script src="js/form-handler.js"></script></body></html>',
        encoding="utf-8",
    )
    runtime = tmp_path / "js" / "aida-zero-forms-1.0.min.js"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text("function t_zeroForms__init(){}", encoding="utf-8")

    result = check_forms_integration(tmp_path)

    assert result.forms_found == 1
    assert result.forms_hooked == 1
    assert result.warnings == 1


def test_forms_check_accepts_rewritten_zero_forms_runtime(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    page.write_text(
        '<html><body><div class="tn-atom__form"></div>'
        '<script src="js/form-handler.js"></script></body></html>',
        encoding="utf-8",
    )
    runtime = tmp_path / "js" / "aida-zero-forms-1.0.min.js"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text("function ai_zeroForms__init(){}", encoding="utf-8")

    result = check_forms_integration(tmp_path)

    assert result.forms_found == 1
    assert result.forms_hooked == 1
    assert result.warnings == 0
