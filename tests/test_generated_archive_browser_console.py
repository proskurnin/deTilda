from __future__ import annotations

import sys
import threading
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest.importorskip("playwright.sync_api")

from playwright.sync_api import Error as PlaywrightError  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from core.api import process_archive  # noqa: E402


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


def _make_tilda_zip(tmp_path: Path) -> Path:
    workdir = tmp_path / "_workdir"
    workdir.mkdir()
    for subdir in ("config", "resources"):
        src = ROOT / subdir
        if src.exists():
            (tmp_path / subdir).symlink_to(src)

    zip_path = workdir / "site.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(
            "site/index.html",
            (
                "<html><head><title>Smoke</title></head><body "
                'data-aida-export="yes"><main>ok</main></body></html>'
            ),
        )
        zf.writestr("site/404.html", "<html><body>404</body></html>")
        zf.writestr("site/htaccess", "RewriteEngine On\n")
        zf.writestr("site/sitemap.xml", "<?xml version='1.0'?><urlset></urlset>")
        zf.writestr("site/readme.txt", "Tilda export")
        zf.writestr("site/robots.txt", "Host: example.com\n")
    return zip_path


def test_generated_archive_has_no_browser_console_errors(tmp_path: Path) -> None:
    archive_path = _make_tilda_zip(tmp_path)
    stats = process_archive(archive_path, logs_dir=tmp_path / "logs")
    assert stats.project_root is not None

    handler = lambda *args, **kwargs: _QuietHandler(  # noqa: E731
        *args,
        directory=str(stats.project_root),
        **kwargs,
    )
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    except PermissionError as exc:
        pytest.skip(f"Local HTTP bind is not available: {exc}")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    console_errors: list[str] = []
    page_errors: list[str] = []
    try:
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch()
            except PlaywrightError as exc:
                pytest.skip(f"Playwright Chromium is not available: {exc}")
            page = browser.new_page()
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))
            page.goto(f"http://127.0.0.1:{server.server_port}/index.html", wait_until="networkidle")
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)

    assert page_errors == []
    assert console_errors == []
