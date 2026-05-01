"""Browser-runtime discovery and localization of CDN assets.

This module is a best-effort post-pass for assets that only appear after JS
executes in a browser. Static, deterministic localization remains in
core.cdn_localizer; this module only augments it when Playwright/Chromium is
available in the runtime environment.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from core import cdn_localizer, logger, utils

__all__ = [
    "BrowserRuntimeAssetResult",
    "collect_browser_pages",
    "localize_browser_runtime_assets",
]


@dataclass
class BrowserRuntimeAssetResult:
    skipped: bool = False
    skip_reason: str = ""
    pages_checked: int = 0
    requests_seen: int = 0
    cdn_requests_seen: int = 0
    downloaded: int = 0
    failed: int = 0
    localized_after_rewrite: int = 0
    failed_urls: list[str] = field(default_factory=list)


def collect_browser_pages(project_root: Path, max_pages: int = 20) -> list[Path]:
    """Return HTML pages worth opening in a browser.

    Tilda body fragments under files/*body.html are not standalone pages, so
    they are skipped. Real pages are opened in stable sorted order.
    """
    project_root = Path(project_root)
    pages: list[Path] = []
    for path in utils.list_files_recursive(project_root, extensions=(".html", ".htm")):
        if path.parent.name == "files" and path.stem.endswith("body"):
            continue
        pages.append(path)
    return sorted(pages)[:max(0, max_pages)]


async def _collect_runtime_cdn_urls(
    pages: list[Path],
    *,
    timeout_ms: int,
    wait_ms: int,
) -> tuple[int, int, set[str]]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed") from exc

    total_requests = 0
    cdn_urls: set[str] = set()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page()

            def _on_request(request) -> None:
                nonlocal total_requests
                total_requests += 1
                if cdn_localizer.is_static_tilda_cdn_url(request.url):
                    cdn_urls.add(request.url)

            page.on("request", _on_request)

            for html_page in pages:
                try:
                    await page.goto(html_page.resolve().as_uri(), wait_until="networkidle", timeout=timeout_ms)
                    if wait_ms > 0:
                        await page.wait_for_timeout(wait_ms)
                except Exception as exc:
                    logger.warn(f"[browser_assets] Не удалось открыть {html_page.name}: {exc}")
        finally:
            await browser.close()

    return total_requests, len(cdn_urls), cdn_urls


def localize_browser_runtime_assets(
    project_root: Path,
    *,
    max_pages: int = 20,
    timeout_sec: int = 20,
    wait_ms: int = 1000,
) -> BrowserRuntimeAssetResult:
    """Open project pages in Chromium and download runtime CDN assets.

    If Playwright or browser binaries are not available, returns skipped=True.
    """
    project_root = Path(project_root)
    result = BrowserRuntimeAssetResult()
    pages = collect_browser_pages(project_root, max_pages=max_pages)
    result.pages_checked = len(pages)
    if not pages:
        result.skipped = True
        result.skip_reason = "no html pages"
        return result

    try:
        requests_seen, cdn_count, cdn_urls = asyncio.run(
            _collect_runtime_cdn_urls(
                pages,
                timeout_ms=max(1, int(timeout_sec * 1000)),
                wait_ms=max(0, int(wait_ms)),
            )
        )
    except RuntimeError as exc:
        result.skipped = True
        result.skip_reason = str(exc)
        return result
    except Exception as exc:
        result.skipped = True
        result.skip_reason = f"browser runtime failed: {exc}"
        return result

    result.requests_seen = requests_seen
    result.cdn_requests_seen = cdn_count
    if not cdn_urls:
        return result

    cache: dict[str, object] = {}
    for url in sorted(cdn_urls):
        local = cdn_localizer.download_cdn_url(url, project_root, cache=cache)
        if local is None:
            result.failed += 1
            result.failed_urls.append(url)
        else:
            result.downloaded += 1

    # Now that runtime-discovered files exist locally, run the static rewriter
    # again. Existing files are reused and no extra network fetch is needed.
    rewrite = cdn_localizer.localize_cdn_urls(project_root)
    result.localized_after_rewrite = rewrite.urls_localized
    return result
