"""Tests for tools/smoke_test_form.py — POSTs Name=Test to send_email.php."""
from __future__ import annotations

import io
import json
import sys
import types
import urllib.error
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "yaml" not in sys.modules:
    yaml_stub = types.ModuleType("yaml")
    yaml_stub.safe_load = lambda *_args, **_kwargs: {}
    sys.modules["yaml"] = yaml_stub

# Импортим модуль через путь, потому что tools/ не пакет
import importlib.util

_SPEC = importlib.util.spec_from_file_location(
    "smoke_test_form",
    ROOT / "tools" / "smoke_test_form.py",
)
assert _SPEC and _SPEC.loader
smoke = importlib.util.module_from_spec(_SPEC)
sys.modules["smoke_test_form"] = smoke  # требуется @dataclass на Py 3.13+
_SPEC.loader.exec_module(smoke)  # type: ignore[union-attr]


class _FakeResponse:
    def __init__(self, status: int, payload: Any) -> None:
        self._status = status
        self._body = (
            json.dumps(payload).encode("utf-8") if not isinstance(payload, bytes) else payload
        )

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_exc: Any) -> None:
        return None

    def getcode(self) -> int:
        return self._status

    def read(self) -> bytes:
        return self._body


def _patch_urlopen(monkeypatch, response: _FakeResponse | Exception) -> list[Any]:
    """Заменяет urlopen на фейк, записывает все запросы в captured."""
    captured: list[Any] = []

    def fake_urlopen(request, timeout=None, context=None):
        captured.append({
            "url": request.full_url,
            "method": request.get_method(),
            "headers": dict(request.header_items()),
            "body": request.data,
            "timeout": timeout,
            "context": context,
        })
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(smoke.urllib.request, "urlopen", fake_urlopen)
    return captured


def test_build_endpoint_appends_send_email_php() -> None:
    assert smoke._build_endpoint("https://example.com") == "https://example.com/send_email.php"
    assert smoke._build_endpoint("https://example.com/") == "https://example.com/send_email.php"


def test_build_endpoint_keeps_explicit_php_path() -> None:
    url = "https://example.com/api/send_email.php"
    assert smoke._build_endpoint(url) == url


def test_build_endpoint_rejects_invalid_url() -> None:
    import pytest
    with pytest.raises(ValueError):
        smoke._build_endpoint("not-a-url")


def test_run_smoke_test_success(monkeypatch) -> None:
    """Сервер вернул ok=true и mode=test → smoke прошёл."""
    captured = _patch_urlopen(
        monkeypatch,
        _FakeResponse(200, {
            "ok": True,
            "message": "Заявка отправлена",
            "mode": "test",
            "recipients": ["r@prororo.com"],
        }),
    )

    result = smoke.run_smoke_test(
        base_url="https://example.com",
        expected_recipients=["r@prororo.com"],
        name="Test deTilda smoke",
        email="r@prororo.com",
    )

    assert result.ok is True
    assert result.status_code == 200
    # XHR-хидер передан, иначе send_email.php не вернёт JSON
    assert captured[0]["headers"]["X-requested-with"] == "XMLHttpRequest"
    assert captured[0]["url"] == "https://example.com/send_email.php"
    assert captured[0]["method"] == "POST"
    assert b"Name=Test" in captured[0]["body"]


def test_run_smoke_test_fails_on_non_200(monkeypatch) -> None:
    error = urllib.error.HTTPError(
        url="https://example.com/send_email.php",
        code=500,
        msg="Server Error",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(b'{"ok":false,"message":"mail failed"}'),
    )
    _patch_urlopen(monkeypatch, error)

    result = smoke.run_smoke_test(
        base_url="https://example.com",
        expected_recipients=["r@prororo.com"],
        name="Test",
        email="r@prororo.com",
    )

    assert result.ok is False
    assert result.status_code == 500


def test_run_smoke_test_fails_on_ok_false(monkeypatch) -> None:
    _patch_urlopen(
        monkeypatch,
        _FakeResponse(200, {"ok": False, "message": "Поле Name обязательно"}),
    )

    result = smoke.run_smoke_test(
        base_url="https://example.com",
        expected_recipients=["r@prororo.com"],
        name="Test",
        email="r@prororo.com",
    )

    assert result.ok is False
    assert "Поле Name" in result.message


def test_run_smoke_test_fails_when_mode_is_not_test(monkeypatch) -> None:
    """Сервер ответил mode=main — значит is_test_submission не сработал
    (например, Name='John' вместо 'Test ...'). Smoke помечает это как fail."""
    _patch_urlopen(
        monkeypatch,
        _FakeResponse(200, {
            "ok": True,
            "mode": "main",
            "recipients": ["info@example.com"],
        }),
    )

    result = smoke.run_smoke_test(
        base_url="https://example.com",
        expected_recipients=["r@prororo.com"],
        name="Some real name",
        email="r@prororo.com",
    )

    assert result.ok is False
    assert "mode" in result.message


def test_run_smoke_test_fails_when_recipients_dont_match(monkeypatch) -> None:
    _patch_urlopen(
        monkeypatch,
        _FakeResponse(200, {
            "ok": True,
            "mode": "test",
            "recipients": ["someone-else@example.com"],
        }),
    )

    result = smoke.run_smoke_test(
        base_url="https://example.com",
        expected_recipients=["r@prororo.com"],
        name="Test",
        email="r@prororo.com",
    )

    assert result.ok is False
    assert "не совпадает" in result.message


def test_main_exits_2_when_no_recipients(monkeypatch, capsys) -> None:
    """Без test_recipients и без --email — exit 2."""
    from core.schemas import FormsConfig

    class _EmptyLoader:
        def __init__(self, _root):
            pass
        def forms(self):
            return FormsConfig(test_recipients=[])

    monkeypatch.setattr(smoke, "ConfigLoader", _EmptyLoader)

    code = smoke.main(["https://example.com"])
    assert code == 2
    err = capsys.readouterr().err
    assert "test_recipients" in err
