"""Tests for core.font_substitute — replace Tilda Sans with Google Manrope."""
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

from core import font_substitute


def test_dedicated_fonts_css_replaced_with_google_import(tmp_path: Path) -> None:
    """fonts-aidasans.css полностью заменяется на @import Manrope."""
    css = tmp_path / "css" / "fonts-aidasans.css"
    css.parent.mkdir()
    css.write_text(
        "@font-face{font-family:'TildaSans';"
        "src:url(https://static.tildacdn.com/fonts/tildasans/tildasans-regular.woff2)}",
        encoding="utf-8",
    )

    font_substitute.substitute_tilda_fonts(tmp_path)

    text = css.read_text(encoding="utf-8")
    assert "fonts.googleapis.com/css2?family=Manrope" in text
    assert "tildacdn" not in text
    assert "TildaSans" not in text


def test_dedicated_tildasans_filename_also_handled(tmp_path: Path) -> None:
    """fonts-tildasans.css (до refs) тоже подхватывается."""
    css = tmp_path / "css" / "fonts-tildasans.css"
    css.parent.mkdir()
    css.write_text("@font-face{font-family:'TildaSans';src:url(x)}", encoding="utf-8")

    font_substitute.substitute_tilda_fonts(tmp_path)

    assert "Manrope" in css.read_text(encoding="utf-8")


def test_font_family_token_replaced_in_css(tmp_path: Path) -> None:
    """font-family: 'aidaSans', Arial → 'Manrope', Arial."""
    css = tmp_path / "main.css"
    css.write_text(
        "body{--ai-headline-font:'aidaSans',Arial,sans-serif;"
        "--ai-text-font:'aidaSans',Arial,sans-serif}",
        encoding="utf-8",
    )

    font_substitute.substitute_tilda_fonts(tmp_path)

    text = css.read_text(encoding="utf-8")
    assert "aidaSans" not in text
    assert "'Manrope'" in text
    # Стек шрифтов сохранён
    assert "Arial,sans-serif" in text


def test_font_family_token_in_html_inline_style(tmp_path: Path) -> None:
    """font-family в inline-style HTML тоже заменяется."""
    html = tmp_path / "page.html"
    html.write_text(
        '<div style="font-family:\'TildaSans\',sans-serif">x</div>',
        encoding="utf-8",
    )

    font_substitute.substitute_tilda_fonts(tmp_path)

    text = html.read_text(encoding="utf-8")
    assert "TildaSans" not in text
    assert "'Manrope'" in text


def test_case_variants_handled(tmp_path: Path) -> None:
    """TildaSans, tildasans, AidaSans, aidaSans — все варианты ловим."""
    css = tmp_path / "x.css"
    css.write_text(
        ".a{font-family:'TildaSans'}"
        ".b{font-family:'tildasans'}"
        ".c{font-family:'AidaSans'}"
        ".d{font-family:'aidaSans'}",
        encoding="utf-8",
    )

    font_substitute.substitute_tilda_fonts(tmp_path)

    text = css.read_text(encoding="utf-8")
    assert text.count("'Manrope'") == 4
    assert "TildaSans" not in text
    assert "AidaSans" not in text
    assert "tildasans" not in text
    assert "aidaSans" not in text


def test_stray_font_face_block_removed_in_other_css(tmp_path: Path) -> None:
    """@font-face с TildaSans в обычном CSS — удаляется, к первому файлу
    добавляется @import (если выделенного файла нет)."""
    css = tmp_path / "weird.css"
    css.write_text(
        "@font-face{font-family:'TildaSans';"
        "src:url(https://static.aidacdn.com/fonts/x.woff2)}\n"
        ".x{color:red}",
        encoding="utf-8",
    )

    font_substitute.substitute_tilda_fonts(tmp_path)

    text = css.read_text(encoding="utf-8")
    assert "@font-face" not in text
    assert "tildacdn" not in text
    assert "aidacdn" not in text
    assert "fonts.googleapis.com" in text
    # Полезные правила сохранены
    assert ".x{color:red}" in text


def test_no_double_import_when_dedicated_file_exists(tmp_path: Path) -> None:
    """Если есть выделенный fonts-aidasans.css — @import не дублируется в другие CSS."""
    dedicated = tmp_path / "fonts-aidasans.css"
    dedicated.write_text("@font-face{font-family:'TildaSans';src:url(x)}", encoding="utf-8")

    other = tmp_path / "other.css"
    other.write_text("@font-face{font-family:'TildaSans';src:url(y)}", encoding="utf-8")

    font_substitute.substitute_tilda_fonts(tmp_path)

    # @import только в dedicated
    assert "fonts.googleapis.com" in dedicated.read_text(encoding="utf-8")
    other_text = other.read_text(encoding="utf-8")
    assert "fonts.googleapis.com" not in other_text
    # Но @font-face всё равно удалён
    assert "@font-face" not in other_text


def test_does_not_match_unquoted_substring(tmp_path: Path) -> None:
    """`tildasans` без кавычек (например в URL `aidasans-vf.woff2`) не трогается."""
    css = tmp_path / "x.css"
    # Имя файла содержит aidasans но не должно попасть под замену
    css.write_text("/* link to aidasans-vf.woff2 in comment */ .x{color:red}", encoding="utf-8")

    font_substitute.substitute_tilda_fonts(tmp_path)

    text = css.read_text(encoding="utf-8")
    # Без кавычек — не трогаем
    assert "aidasans-vf.woff2" in text


def test_returns_zero_when_no_tilda_fonts(tmp_path: Path) -> None:
    """Чистый проект без Tilda — модуль ничего не делает."""
    (tmp_path / "main.css").write_text("body{color:red}", encoding="utf-8")

    n = font_substitute.substitute_tilda_fonts(tmp_path)

    assert n == 0


def test_idempotent(tmp_path: Path) -> None:
    """Повторный запуск ничего не меняет."""
    css = tmp_path / "fonts-aidasans.css"
    css.write_text("@font-face{font-family:'TildaSans';src:url(x)}", encoding="utf-8")

    font_substitute.substitute_tilda_fonts(tmp_path)
    after_first = css.read_text(encoding="utf-8")

    font_substitute.substitute_tilda_fonts(tmp_path)
    after_second = css.read_text(encoding="utf-8")

    assert after_first == after_second
