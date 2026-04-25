"""Tests for core.forms — copies form handlers from resources/."""
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

from core.forms import generate_form_handler_js, generate_send_email_php


def test_generate_send_email_php_creates_file(tmp_path: Path) -> None:
    """send_email.php копируется в корень проекта из resources/."""
    target = generate_send_email_php(tmp_path)

    assert target == tmp_path / "send_email.php"
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    # Проверяем что это реальный PHP-обработчик, а не пустой файл
    assert "<?php" in content


def test_generate_send_email_php_also_creates_form_handler(tmp_path: Path) -> None:
    """generate_send_email_php должен также создать js/form-handler.js."""
    generate_send_email_php(tmp_path)

    handler = tmp_path / "js" / "form-handler.js"
    assert handler.exists()
    content = handler.read_text(encoding="utf-8")
    # Проверяем что это реальный JS-обработчик форм
    assert "form-handler" in content.lower() or "submit" in content.lower()


def test_generate_form_handler_js_creates_js_directory(tmp_path: Path) -> None:
    """js/ создаётся автоматически если его нет."""
    assert not (tmp_path / "js").exists()
    target = generate_form_handler_js(tmp_path)

    assert target == tmp_path / "js" / "form-handler.js"
    assert target.exists()
    assert (tmp_path / "js").is_dir()


def test_generate_accepts_project_context_object(tmp_path: Path) -> None:
    """generate_send_email_php принимает объект с атрибутом project_root."""
    class FakeContext:
        project_root = tmp_path

    target = generate_send_email_php(FakeContext())
    assert target == tmp_path / "send_email.php"
    assert target.exists()


def test_generate_overwrites_existing_file(tmp_path: Path) -> None:
    """Если файл уже существует — перезаписывается новым из resources/."""
    target = tmp_path / "send_email.php"
    target.write_text("OLD CONTENT", encoding="utf-8")

    generate_send_email_php(tmp_path)

    content = target.read_text(encoding="utf-8")
    assert "OLD CONTENT" not in content
    assert "<?php" in content
