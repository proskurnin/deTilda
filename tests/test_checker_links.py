"""Tests for final HTML link integrity checks."""
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

from core.checker import check_links
from core.schemas import PatternsConfig


class _FakeLoader:
    def __init__(self) -> None:
        self._patterns = PatternsConfig.model_validate({
            "links": [
                r'(?P<attr>href|src|action)\s*=\s*"(?P<link>[^"]+)"',
            ],
            "ignore_prefixes": ["http://", "https://", "//", "data:", "mailto:", "tel:", "#"],
            "htaccess_patterns": {
                "rewrite_rule": "(?im)^[ \\t]*RewriteRule[ \\t]+\\^/?([a-z0-9\\-_/]+)\\??\\$?[ \\t]+([^ \\t]+)",
                "redirect": "(?im)^[ \\t]*Redirect[ \\t]+(/[^ \\t]+)[ \\t]+([^ \\t]+)",
                "remove_unresolved_routes": False,
            },
        })

    def patterns(self) -> PatternsConfig:
        return self._patterns


def test_body_file_accepts_links_relative_to_physical_files_dir(tmp_path: Path) -> None:
    """Tilda body fragments can contain ../page.html links from files/."""
    (tmp_path / "files").mkdir()
    (tmp_path / "page123.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "page456.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "files" / "page123body.html").write_text(
        '<a href="../page456.html">next</a>',
        encoding="utf-8",
    )

    result = check_links(tmp_path, _FakeLoader())

    assert result.checked == 1
    assert result.broken == 0


def test_body_file_accepts_links_relative_to_injected_page(tmp_path: Path) -> None:
    """Injected body fragments also use page-root paths for scripts/assets."""
    (tmp_path / "files").mkdir()
    (tmp_path / "js").mkdir()
    (tmp_path / "page123.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "js" / "form-handler.js").write_text("", encoding="utf-8")
    (tmp_path / "files" / "page123body.html").write_text(
        '<script src="js/form-handler.js"></script>',
        encoding="utf-8",
    )

    result = check_links(tmp_path, _FakeLoader())

    assert result.checked == 1
    assert result.broken == 0


def test_body_file_reports_link_missing_in_both_contexts(tmp_path: Path) -> None:
    (tmp_path / "files").mkdir()
    (tmp_path / "page123.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "files" / "page123body.html").write_text(
        '<a href="../missing.html">missing</a>',
        encoding="utf-8",
    )

    result = check_links(tmp_path, _FakeLoader())

    assert result.checked == 1
    assert result.broken == 1
