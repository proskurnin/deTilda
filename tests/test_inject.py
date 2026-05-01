from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from core.config_loader import ConfigLoader
from core.inject import inject_form_scripts

ROOT = Path(__file__).resolve().parents[1]


def test_inject_adds_ga_into_head_and_form_handler_into_body(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    page.write_text("<html><head><title>X</title></head><body>ok</body></html>", encoding="utf-8")

    updated = inject_form_scripts(tmp_path, ConfigLoader(ROOT))

    content = page.read_text(encoding="utf-8")
    assert updated == 1
    assert '<script defer src="/js/ga-config.js"></script>' in content
    assert '<script defer src="/js/ga.js"></script></head>' in content
    assert '<script src="js/form-handler.js"></script></body>' in content


def test_inject_does_not_duplicate_existing_ga(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    page.write_text(
        (
            '<html><head><script defer src="/js/ga-config.js"></script>'
            '<script defer src="/js/ga.js"></script></head><body>ok</body></html>'
        ),
        encoding="utf-8",
    )

    inject_form_scripts(tmp_path, ConfigLoader(ROOT))

    content = page.read_text(encoding="utf-8")
    assert content.count('src="/js/ga-config.js"') == 1
    assert content.count('src="/js/ga.js"') == 1


def test_inject_does_not_duplicate_legacy_relative_ga(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    page.write_text(
        '<html><head><script src="js/ga.js"></script></head><body>ok</body></html>',
        encoding="utf-8",
    )

    inject_form_scripts(tmp_path, ConfigLoader(ROOT))

    content = page.read_text(encoding="utf-8")
    assert content.count('js/ga.js') == 1
    assert 'src="/js/ga-config.js"' in content


def test_inject_supports_project_context_without_explicit_loader(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    page.write_text("<html><head></head><body>ok</body></html>", encoding="utf-8")
    context = SimpleNamespace(project_root=tmp_path, config_loader=ConfigLoader(ROOT))

    updated = inject_form_scripts(context)

    content = page.read_text(encoding="utf-8")
    assert updated == 1
    assert 'script src="js/form-handler.js"' in content
