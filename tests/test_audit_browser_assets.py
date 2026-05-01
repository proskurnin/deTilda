"""Tests for tools/audit_browser_assets.py pure helpers."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_SPEC = importlib.util.spec_from_file_location(
    "audit_browser_assets",
    ROOT / "tools" / "audit_browser_assets.py",
)
assert _SPEC and _SPEC.loader
audit = importlib.util.module_from_spec(_SPEC)
sys.modules["audit_browser_assets"] = audit
_SPEC.loader.exec_module(audit)  # type: ignore[union-attr]


def test_resolve_target_file_to_file_url(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    page.write_text("<html></html>", encoding="utf-8")

    result = audit.resolve_target(str(page))

    assert result.startswith("file://")
    assert result.endswith("/index.html")


def test_resolve_target_directory_uses_index(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")

    result = audit.resolve_target(str(tmp_path))

    assert result.startswith("file://")
    assert result.endswith("/index.html")


def test_resolve_target_keeps_http_url() -> None:
    assert audit.resolve_target("https://example.com/page") == "https://example.com/page"


def test_infer_project_root_for_file_url(tmp_path: Path) -> None:
    page = tmp_path / "sub" / "page.html"
    page.parent.mkdir()
    page.write_text("<html></html>", encoding="utf-8")
    target = page.resolve().as_uri()

    assert audit.infer_project_root(target, None) == page.parent.resolve()


def test_explicit_project_root_wins(tmp_path: Path) -> None:
    root = tmp_path / "site"
    root.mkdir()

    assert audit.infer_project_root("https://example.com", str(root)) == root.resolve()


def test_is_tilda_asset_url_matches_expected_hosts() -> None:
    assert audit.is_tilda_asset_url("https://static.tildacdn.com/js/x.js")
    assert audit.is_tilda_asset_url("//static.aidacdn.com/js/x.js")
    assert audit.is_tilda_asset_url("https://forms.tilda.cc/procces/")
    assert not audit.is_tilda_asset_url("https://www.googletagmanager.com/gtag/js")


def test_local_candidate_for_url_strips_query(tmp_path: Path) -> None:
    result = audit.local_candidate_for_url(
        "https://static.tildacdn.com/js/tilda-extra.js?t=123",
        tmp_path,
    )

    assert result == tmp_path / "js" / "tilda-extra.js"


def test_text_output_lists_requests(tmp_path: Path) -> None:
    item = audit.AssetRequest(
        url="https://static.tildacdn.com/js/x.js",
        method="GET",
        resource_type="script",
        status=200,
        local_path=str(tmp_path / "js" / "x.js"),
        local_exists=False,
    )
    result = audit.AuditResult(
        target="file:///site/index.html",
        project_root="/site",
        total_requests=3,
        tilda_requests=[item],
    )

    text = audit._format_text(result)

    assert "Tilda/CDN requests: 1" in text
    assert "https://static.tildacdn.com/js/x.js" in text
    assert "exists=False" in text
