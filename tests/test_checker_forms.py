from __future__ import annotations

from pathlib import Path

from core.checker import check_forms_integration, smoke_check_zero_forms_runtime


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
    (tmp_path / "css").mkdir(parents=True, exist_ok=True)
    (tmp_path / "css" / "aida-zero-form-horizontal.min.css").write_text("", encoding="utf-8")
    (tmp_path / "css" / "aida-zero-form-errorbox.min.css").write_text("", encoding="utf-8")
    (tmp_path / "js" / "aida-forms-1.0.min.js").write_text("function aidaForm_initMasks(){}", encoding="utf-8")
    (tmp_path / "js" / "aida-fallback-1.0.min.js").write_text("function ai_fallback__reloadSRC(){}", encoding="utf-8")

    result = check_forms_integration(tmp_path)

    assert result.forms_found == 1
    assert result.forms_hooked == 1
    assert result.warnings == 0


def test_forms_check_warns_when_zero_form_dependencies_missing(tmp_path: Path) -> None:
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
    assert result.warnings == 1


def test_forms_check_accepts_zero_block_form_without_separate_runtime(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    page.write_text(
        '<html><body><div class="tn-atom__form"></div>'
        '<script src="js/form-handler.js"></script></body></html>',
        encoding="utf-8",
    )

    result = check_forms_integration(tmp_path)

    assert result.forms_found == 1
    assert result.forms_hooked == 1
    assert result.warnings == 0


def test_zero_form_smoke_skips_project_without_zero_forms(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html><body>plain</body></html>", encoding="utf-8")

    result = smoke_check_zero_forms_runtime(tmp_path)

    assert result.checked is False
    assert result.failed is False


def test_zero_form_smoke_skips_zero_block_form_without_separate_runtime(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        '<html><body><div class="tn-atom__form"></div></body></html>',
        encoding="utf-8",
    )

    result = smoke_check_zero_forms_runtime(tmp_path)

    assert result.checked is False
    assert result.failed is False


def test_zero_form_smoke_passes_rewritten_runtime(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        '<html><body><script>ai_zeroForms__init("123")</script></body></html>',
        encoding="utf-8",
    )
    runtime = tmp_path / "js" / "aida-zero-forms-1.0.min.js"
    runtime.parent.mkdir()
    runtime.write_text(
        "function ai_zeroForms__init(){}"
        "/* deTilda zero-forms namespace bridge */"
        "/* deTilda zero-forms local resource base */",
        encoding="utf-8",
    )

    result = smoke_check_zero_forms_runtime(tmp_path)

    assert result.checked is True
    assert result.failed is False


def test_zero_form_smoke_fails_invalid_runtime(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        '<html><body><script>ai_zeroForms__init("123")</script></body></html>',
        encoding="utf-8",
    )
    runtime = tmp_path / "js" / "aida-zero-forms-1.0.min.js"
    runtime.parent.mkdir()
    runtime.write_text("function t_zeroForms__init(){}", encoding="utf-8")

    result = smoke_check_zero_forms_runtime(tmp_path)

    assert result.checked is True
    assert result.failed is True
    assert result.messages
