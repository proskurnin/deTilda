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


def _make_context_with_recipients(project_root: Path, recipients):
    """Контекст с config_loader, возвращающим заданные test_recipients."""
    from core.schemas import FormsConfig

    class FakeLoader:
        def forms(self):
            return FormsConfig(test_recipients=list(recipients))

    class FakeContext:
        pass

    ctx = FakeContext()
    ctx.project_root = project_root
    ctx.config_loader = FakeLoader()
    return ctx


def test_send_email_test_recipients_replaced_from_config(tmp_path: Path) -> None:
    """forms.test_recipients из конфига подставляются в const TEST_RECIPIENTS."""
    from core.config_loader import ConfigLoader

    # Реальный ConfigLoader, чтобы isinstance-проверка прошла
    class _Loader(ConfigLoader):
        def forms(self):
            from core.schemas import FormsConfig
            return FormsConfig(test_recipients=["alice@example.com", "bob@example.com"])

    class FakeContext:
        project_root = tmp_path
        config_loader = _Loader(ROOT)

    generate_send_email_php(FakeContext())

    content = (tmp_path / "send_email.php").read_text(encoding="utf-8")
    assert "'alice@example.com'" in content or '"alice@example.com"' in content
    assert "'bob@example.com'" in content or '"bob@example.com"' in content
    # Дефолтный адрес из шаблона должен быть заменён
    assert "'r@prororo.com'" not in content


def test_send_email_keeps_template_default_when_recipients_empty(tmp_path: Path) -> None:
    """Пустой test_recipients — шаблон копируется как есть, без подмены."""
    from core.config_loader import ConfigLoader

    class _Loader(ConfigLoader):
        def forms(self):
            from core.schemas import FormsConfig
            return FormsConfig(test_recipients=[])

    class FakeContext:
        project_root = tmp_path
        config_loader = _Loader(ROOT)

    generate_send_email_php(FakeContext())

    content = (tmp_path / "send_email.php").read_text(encoding="utf-8")
    # Дефолт из шаблона сохранён
    assert "r@prororo.com" in content


def test_send_email_recipients_quotes_are_escaped(tmp_path: Path) -> None:
    """Email с потенциально опасными символами не ломает PHP-литерал."""
    from core.config_loader import ConfigLoader

    class _Loader(ConfigLoader):
        def forms(self):
            from core.schemas import FormsConfig
            return FormsConfig(test_recipients=['weird"quote@example.com'])

    class FakeContext:
        project_root = tmp_path
        config_loader = _Loader(ROOT)

    generate_send_email_php(FakeContext())

    content = (tmp_path / "send_email.php").read_text(encoding="utf-8")
    # json.dumps экранирует кавычку как \"
    assert '\\"' in content
