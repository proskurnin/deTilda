"""Verify deployed /health endpoint version."""
from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.utils import load_manifest


def _health_url(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    return base_url if base_url.endswith("/health") else base_url + "/health"


def _fetch_json(url: str, timeout: float, insecure: bool) -> dict[str, Any]:
    context = ssl._create_unverified_context() if insecure else None
    with urllib.request.urlopen(url, timeout=timeout, context=context) as resp:
        payload = resp.read().decode("utf-8", errors="replace")
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("health response is not a JSON object")
    return data


def verify_health(
    base_url: str,
    expected_version: str,
    *,
    attempts: int = 5,
    delay_sec: float = 2.0,
    timeout: float = 10.0,
    insecure: bool = False,
) -> tuple[bool, str]:
    url = _health_url(base_url)
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            data = _fetch_json(url, timeout=timeout, insecure=insecure)
            actual = str(data.get("version", ""))
            status = str(data.get("status", ""))
            if status == "ok" and actual == expected_version:
                return True, f"{url}: version={actual}"
            last_error = (
                f"{url}: status={status!r}, version={actual!r}, "
                f"expected={expected_version!r}"
            )
        except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
            last_error = f"{url}: {exc}"
        if attempt < attempts:
            time.sleep(delay_sec)
    return False, last_error


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify deTilda /health version.")
    parser.add_argument("urls", nargs="+", help="Base URLs or direct /health URLs")
    parser.add_argument("--expected-version", default=None)
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument("--delay-sec", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--insecure", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    expected = args.expected_version or str(load_manifest().get("version", ""))
    if not expected:
        print("Expected version is empty", file=sys.stderr)
        return 2

    ok = True
    for url in args.urls:
        passed, message = verify_health(
            url,
            expected,
            attempts=args.attempts,
            delay_sec=args.delay_sec,
            timeout=args.timeout,
            insecure=args.insecure,
        )
        print(("OK " if passed else "FAIL ") + message)
        ok = ok and passed
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
