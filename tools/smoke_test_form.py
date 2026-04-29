"""CLI smoke-test для send_email.php после деплоя.

Делает POST на `<url>/send_email.php` с Name='Test deTilda smoke' (это
триггерит test-режим в send_email.php — письмо уйдёт на TEST_RECIPIENTS,
заданные в config.yaml: forms.test_recipients).

Проверяет:
  - HTTP 200
  - ответ JSON с ok=true, mode='test'
  - список recipients совпадает с config.forms.test_recipients

Запуск:
    python3 tools/smoke_test_form.py https://hotelsargis.ru

Опции:
    --name       переопределить Name (по умолчанию "Test deTilda smoke")
    --email      переопределить Email (по умолчанию первый из test_recipients)
    --timeout    таймаут запроса в секундах (по умолчанию 15)
    --insecure   отключить проверку SSL-сертификата

Exit code:
    0 — форма работает, тестовое письмо принято
    1 — неудача (HTTP-ошибка, невалидный JSON, ok=false, mode != test)
    2 — ошибка конфигурации (test_recipients не задан и --email не передан)
"""
from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Когда запускается напрямую (`python3 tools/smoke_test_form.py`), родителя
# в sys.path нет — добавляем корень репозитория.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.config_loader import ConfigLoader

DEFAULT_NAME = "Test deTilda smoke"
DEFAULT_TIMEOUT = 15.0
ENDPOINT_PATH = "/send_email.php"


@dataclass
class SmokeResult:
    ok: bool
    status_code: int
    payload: dict[str, Any]
    message: str


def _build_endpoint(base_url: str) -> str:
    """Возвращает абсолютный URL до send_email.php.

    Принимает либо корень сайта (`https://example.com`), либо уже полный
    URL до эндпоинта (`https://example.com/send_email.php`).
    """
    parsed = urllib.parse.urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Не валидный URL: {base_url!r}")
    if parsed.path.endswith(".php"):
        return base_url
    base = base_url.rstrip("/")
    return base + ENDPOINT_PATH


def _post_form(
    endpoint: str,
    name: str,
    email: str,
    timeout: float,
    insecure: bool,
) -> tuple[int, dict[str, Any]]:
    """POST'ит форму как XHR; возвращает (status, parsed_json)."""
    body = urllib.parse.urlencode({"Name": name, "Email": email}).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        },
    )

    context = ssl._create_unverified_context() if insecure else None
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as resp:
            status = resp.getcode()
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""

    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {"_raw": raw[:500]}

    if not isinstance(payload, dict):
        payload = {"_raw": str(payload)[:500]}

    return status, payload


def run_smoke_test(
    base_url: str,
    expected_recipients: list[str],
    name: str,
    email: str,
    timeout: float = DEFAULT_TIMEOUT,
    insecure: bool = False,
) -> SmokeResult:
    """Запускает smoke-test и возвращает структурированный результат."""
    endpoint = _build_endpoint(base_url)
    status, payload = _post_form(endpoint, name, email, timeout, insecure)

    if status != 200:
        return SmokeResult(False, status, payload, f"HTTP {status}, ожидалось 200")

    if not payload.get("ok"):
        message = payload.get("message", "send_email.php вернул ok=false")
        return SmokeResult(False, status, payload, str(message))

    if payload.get("mode") != "test":
        return SmokeResult(
            False,
            status,
            payload,
            f"mode={payload.get('mode')!r}, ожидался 'test' — Name не распознан как тестовый",
        )

    actual = payload.get("recipients") or []
    if expected_recipients and set(actual) != set(expected_recipients):
        return SmokeResult(
            False,
            status,
            payload,
            f"recipients={actual!r} не совпадает с config={expected_recipients!r}",
        )

    return SmokeResult(True, status, payload, f"OK — письмо отправлено на {actual}")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke-test send_email.php после деплоя сайта.",
    )
    parser.add_argument(
        "url",
        help="URL сайта, например https://hotelsargis.ru (или полный путь к send_email.php)",
    )
    parser.add_argument("--name", default=DEFAULT_NAME, help="значение поля Name")
    parser.add_argument("--email", default=None, help="значение поля Email (по умолчанию: первый из test_recipients)")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"таймаут запроса в секундах (по умолчанию {DEFAULT_TIMEOUT:.0f})",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="не проверять SSL-сертификат",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    loader = ConfigLoader(_REPO_ROOT)
    expected = list(loader.forms().test_recipients)
    email = args.email or (expected[0] if expected else None)
    if not email:
        print(
            "❌ Не задан email: forms.test_recipients пуст в config.yaml "
            "и не передан --email",
            file=sys.stderr,
        )
        return 2

    print(f"🚀 Smoke-test: POST {_build_endpoint(args.url)} (Name={args.name!r}, Email={email!r})")

    result = run_smoke_test(
        base_url=args.url,
        expected_recipients=expected,
        name=args.name,
        email=email,
        timeout=args.timeout,
        insecure=args.insecure,
    )

    icon = "✅" if result.ok else "❌"
    print(f"{icon} {result.message}")
    if result.payload:
        print(f"   Ответ: {json.dumps(result.payload, ensure_ascii=False)}")

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
