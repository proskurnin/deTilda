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
