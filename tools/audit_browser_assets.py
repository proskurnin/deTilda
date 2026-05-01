"""Browser-based audit for runtime asset requests.

This is an optional diagnostic tool, not a pipeline step. It opens a processed
HTML page in a real browser via Playwright and reports Tilda/CDN requests that
the static pipeline may not have seen.

Usage:
    python tools/audit_browser_assets.py _workdir/project5641940/page27969817.html
    python tools/audit_browser_assets.py http://localhost:8000/page27969817.html --project-root _workdir/project5641940

Optional dependency:
    python -m pip install playwright
    python -m playwright install chromium

Exit code:
    0 — audit completed; no Tilda/CDN requests observed
    1 — audit completed; Tilda/CDN requests observed
    2 — invalid arguments or Playwright is not installed
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


TILDA_HOST_MARKERS = (
    "tilda.cc",
    "tilda.ws",
    "tildacdn.com",
    "tildacdn.net",
    "tildacdn.pro",
    "aidacdn.com",
    "forms.tilda.",
    "forms.tildacdn.",
    "forms.aidacdn.",
)


@dataclass
class AssetRequest:
    url: str
    method: str
    resource_type: str
    status: int | None = None
    failure: str | None = None
    local_path: str | None = None
    local_exists: bool | None = None


@dataclass
class AuditResult:
    target: str
    project_root: str | None
    total_requests: int
    tilda_requests: list[AssetRequest]

    @property
    def ok(self) -> bool:
        return not self.tilda_requests


def _is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https", "file"}


def resolve_target(target: str) -> str:
    """Return a browser-loadable URL for a path or URL target."""
    if _is_url(target):
        return target

    path = Path(target).expanduser().resolve()
    if path.is_dir():
        path = path / "index.html"
    if not path.exists():
        raise ValueError(f"target not found: {path}")
    return path.as_uri()


def infer_project_root(target: str, project_root: str | None) -> Path | None:
    """Infer project root for local file targets unless explicitly provided."""
    if project_root:
        return Path(project_root).expanduser().resolve()

    parsed = urlparse(target)
    if parsed.scheme != "file":
        return None

    path = Path(unquote(parsed.path)).resolve()
    if path.is_dir():
        return path
    return path.parent


def is_tilda_asset_url(url: str) -> bool:
    parsed = urlparse(url if not url.startswith("//") else f"https:{url}")
    host = parsed.netloc.lower()
    return any(marker in host for marker in TILDA_HOST_MARKERS)


def local_candidate_for_url(url: str, project_root: Path | None) -> Path | None:
    """Map a CDN URL to the local path the pipeline would normally create."""
    if project_root is None:
        return None
    parsed = urlparse(url if not url.startswith("//") else f"https:{url}")
    if not parsed.path or parsed.path.endswith("/"):
        return None
    return project_root / unquote(parsed.path).lstrip("/")


async def run_browser_audit(
    target: str,
    *,
    project_root: Path | None = None,
    timeout_ms: int = 20_000,
    wait_ms: int = 1_000,
    headless: bool = True,
) -> AuditResult:
    """Open target in Chromium and collect Tilda/CDN runtime requests."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - exercised via main()
        raise RuntimeError(
            "Playwright is not installed. Install with: "
            "python -m pip install playwright && python -m playwright install chromium"
        ) from exc

    target_url = resolve_target(target)
    root = project_root or infer_project_root(target_url, None)
    requests_by_url: dict[str, AssetRequest] = {}
    total_requests = 0

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        page = await browser.new_page()

        def _record_request(request) -> None:
            nonlocal total_requests
            total_requests += 1
            url = request.url
            if not is_tilda_asset_url(url):
                return
            local = local_candidate_for_url(url, root)
            requests_by_url[url] = AssetRequest(
                url=url,
                method=request.method,
                resource_type=request.resource_type,
                local_path=str(local) if local else None,
                local_exists=local.exists() if local else None,
            )

        def _record_response(response) -> None:
            item = requests_by_url.get(response.url)
            if item is not None:
                item.status = response.status

        def _record_failure(request) -> None:
            item = requests_by_url.get(request.url)
            if item is not None:
                failure = request.failure
                item.failure = failure.get("errorText") if failure else "request failed"

        page.on("request", _record_request)
        page.on("response", _record_response)
        page.on("requestfailed", _record_failure)

        await page.goto(target_url, wait_until="networkidle", timeout=timeout_ms)
        if wait_ms > 0:
            await page.wait_for_timeout(wait_ms)
        await browser.close()

    return AuditResult(
        target=target_url,
        project_root=str(root) if root else None,
        total_requests=total_requests,
        tilda_requests=sorted(requests_by_url.values(), key=lambda item: item.url),
    )


def _format_text(result: AuditResult) -> str:
    lines = [
        f"Target: {result.target}",
        f"Project root: {result.project_root or '-'}",
        f"Total browser requests: {result.total_requests}",
        f"Tilda/CDN requests: {len(result.tilda_requests)}",
    ]
    if result.tilda_requests:
        lines.append("")
        for item in result.tilda_requests:
            status = item.status if item.status is not None else "-"
            local = item.local_path or "-"
            exists = "-" if item.local_exists is None else str(item.local_exists)
            failure = f" failure={item.failure}" if item.failure else ""
            lines.append(
                f"- {item.resource_type} {status} {item.url}{failure}\n"
                f"  local={local} exists={exists}"
            )
    return "\n".join(lines)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open a page in Chromium and report runtime Tilda/CDN asset requests.",
    )
    parser.add_argument("target", help="HTML file, directory, file:// URL, or http(s) URL")
    parser.add_argument("--project-root", default=None, help="processed site root for local existence checks")
    parser.add_argument("--timeout", type=float, default=20.0, help="page load timeout in seconds")
    parser.add_argument("--wait-ms", type=int, default=1000, help="extra wait after networkidle")
    parser.add_argument("--headed", action="store_true", help="show browser window")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        target_url = resolve_target(args.target)
        project_root = infer_project_root(target_url, args.project_root)
        result = asyncio.run(
            run_browser_audit(
                target_url,
                project_root=project_root,
                timeout_ms=int(args.timeout * 1000),
                wait_ms=args.wait_ms,
                headless=not args.headed,
            )
        )
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        payload: dict[str, Any] = asdict(result)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_format_text(result))

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
