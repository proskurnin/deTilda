"""Tests for core.browser_assets runtime CDN localization."""
from __future__ import annotations

from pathlib import Path

from core import browser_assets, cdn_localizer


def test_collect_browser_pages_skips_tilda_body_fragments(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "page.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "files").mkdir()
    (tmp_path / "files" / "pagebody.html").write_text("<div></div>", encoding="utf-8")

    pages = browser_assets.collect_browser_pages(tmp_path)

    assert pages == [tmp_path / "index.html", tmp_path / "page.html"]


def test_collect_browser_pages_respects_max_pages(tmp_path: Path) -> None:
    for idx in range(3):
        (tmp_path / f"p{idx}.html").write_text("<html></html>", encoding="utf-8")

    pages = browser_assets.collect_browser_pages(tmp_path, max_pages=2)

    assert len(pages) == 2


def test_browser_runtime_skips_without_pages(tmp_path: Path) -> None:
    result = browser_assets.localize_browser_runtime_assets(tmp_path)

    assert result.skipped is True
    assert result.skip_reason == "no html pages"


def test_browser_runtime_downloads_collected_cdn_urls(tmp_path: Path, monkeypatch) -> None:
    page = tmp_path / "index.html"
    page.write_text("<html></html>", encoding="utf-8")

    async def _fake_collect(_pages, *, timeout_ms, wait_ms):
        return 3, 1, {"https://static.tildacdn.com/js/tilda-extra.js"}

    downloaded: list[str] = []

    def _fake_download(url, project_root, cache=None):
        downloaded.append(url)
        target = project_root / "js" / "tilda-extra.js"
        target.parent.mkdir()
        target.write_text("ok", encoding="utf-8")
        return target

    class _RewriteResult:
        urls_localized = 1

    monkeypatch.setattr(browser_assets, "_collect_runtime_cdn_urls", _fake_collect)
    monkeypatch.setattr(cdn_localizer, "download_cdn_url", _fake_download)
    monkeypatch.setattr(cdn_localizer, "localize_cdn_urls", lambda _root: _RewriteResult())

    result = browser_assets.localize_browser_runtime_assets(tmp_path)

    assert result.skipped is False
    assert result.requests_seen == 3
    assert result.cdn_requests_seen == 1
    assert result.downloaded == 1
    assert result.localized_after_rewrite == 1
    assert downloaded == ["https://static.tildacdn.com/js/tilda-extra.js"]


def test_browser_runtime_records_failed_download(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")

    async def _fake_collect(_pages, *, timeout_ms, wait_ms):
        return 1, 1, {"https://static.tildacdn.com/js/missing.js"}

    class _RewriteResult:
        urls_localized = 0

    monkeypatch.setattr(browser_assets, "_collect_runtime_cdn_urls", _fake_collect)
    monkeypatch.setattr(cdn_localizer, "download_cdn_url", lambda *_args, **_kw: None)
    monkeypatch.setattr(cdn_localizer, "localize_cdn_urls", lambda _root: _RewriteResult())

    result = browser_assets.localize_browser_runtime_assets(tmp_path)

    assert result.failed == 1
    assert result.failed_urls == ["https://static.tildacdn.com/js/missing.js"]
