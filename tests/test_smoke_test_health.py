from __future__ import annotations

from tools import smoke_test_health


def test_verify_health_accepts_matching_version(monkeypatch) -> None:
    monkeypatch.setattr(
        smoke_test_health,
        "_fetch_json",
        lambda *_args, **_kwargs: {"status": "ok", "version": "1.2.3"},
    )

    ok, message = smoke_test_health.verify_health(
        "https://example.com",
        "1.2.3",
        attempts=1,
    )

    assert ok is True
    assert "version=1.2.3" in message


def test_verify_health_rejects_version_mismatch(monkeypatch) -> None:
    monkeypatch.setattr(
        smoke_test_health,
        "_fetch_json",
        lambda *_args, **_kwargs: {"status": "ok", "version": "1.2.2"},
    )

    ok, message = smoke_test_health.verify_health(
        "https://example.com/health",
        "1.2.3",
        attempts=1,
    )

    assert ok is False
    assert "expected='1.2.3'" in message
