"""Tests for web/app.py FastAPI endpoints."""
from __future__ import annotations

import io
import sys
import time
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from web.app import app, _STORE  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _make_zip(name: str = "site") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{name}/index.html", "<html><body>test</body></html>")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# /api/config
# ---------------------------------------------------------------------------

def test_config_returns_web_settings(client: TestClient) -> None:
    r = client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert "max_upload_size_mb" in data
    assert "allowed_extensions" in data
    assert ".zip" in data["allowed_extensions"]


# ---------------------------------------------------------------------------
# POST /api/jobs
# ---------------------------------------------------------------------------

def test_create_job_returns_202(client: TestClient) -> None:
    r = client.post(
        "/api/jobs",
        files={"file": ("site.zip", _make_zip(), "application/zip")},
        data={"email": "test@example.com"},
    )
    assert r.status_code == 202
    body = r.json()
    assert "job_id" in body
    assert body["status"] in ("pending", "running", "done")


def test_create_job_rejects_non_zip(client: TestClient) -> None:
    r = client.post(
        "/api/jobs",
        files={"file": ("site.tar.gz", b"fake", "application/gzip")},
        data={"email": ""},
    )
    assert r.status_code == 400


def test_create_job_rejects_oversized_file(client: TestClient, monkeypatch) -> None:
    from web import app as app_module
    from core.schemas import WebConfig

    monkeypatch.setattr(
        app_module._CONFIG, "_cache",
        app_module._CONFIG._load().__class__(
            **{**app_module._CONFIG._load().__dict__, "web": WebConfig(max_upload_size_mb=0)}
        ),
        raising=False,
    )
    # Patch the web() method to return tiny limit
    original_web = app_module._CONFIG.web
    app_module._CONFIG.web = lambda: WebConfig(max_upload_size_mb=0)

    try:
        r = client.post(
            "/api/jobs",
            files={"file": ("site.zip", _make_zip(), "application/zip")},
            data={"email": ""},
        )
        assert r.status_code == 413
    finally:
        app_module._CONFIG.web = original_web


# ---------------------------------------------------------------------------
# GET /api/jobs/{id}
# ---------------------------------------------------------------------------

def test_get_job_not_found(client: TestClient) -> None:
    r = client.get("/api/jobs/nonexistent-id")
    assert r.status_code == 404


def test_get_job_returns_status(client: TestClient) -> None:
    create = client.post(
        "/api/jobs",
        files={"file": ("site.zip", _make_zip(), "application/zip")},
        data={"email": ""},
    )
    assert create.status_code == 202
    job_id = create.json()["job_id"]

    r = client.get(f"/api/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json()["id"] == job_id
    assert "status" in r.json()


# ---------------------------------------------------------------------------
# GET /api/jobs/{id}/download — job not done
# ---------------------------------------------------------------------------

def test_download_not_done_returns_409(client: TestClient) -> None:
    """Download before job finishes returns 409."""
    job = _STORE.create()
    # job.status stays PENDING
    r = client.get(f"/api/jobs/{job.id}/download")
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# Admin panel — auth
# ---------------------------------------------------------------------------

def test_admin_requires_auth(client: TestClient) -> None:
    r = client.get("/admin")
    assert r.status_code == 401


def test_admin_rejects_wrong_password(client: TestClient, monkeypatch) -> None:
    import os
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    r = client.get("/admin", auth=("admin", "wrong"))
    assert r.status_code == 401


def test_admin_accepts_correct_credentials(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    r = client.get("/admin", auth=("admin", "secret"))
    assert r.status_code == 200
    assert "deTilda" in r.text
    # Token must be injected into the page (not left as placeholder)
    assert "__ADMIN_TOKEN__" not in r.text


def test_admin_stats_returns_json(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    r = client.get("/admin/api/stats", auth=("admin", "secret"))
    assert r.status_code == 200
    data = r.json()
    assert "total_jobs" in data
    assert "config" in data


def test_admin_cleanup_returns_removed_count(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    r = client.post("/admin/api/cleanup", auth=("admin", "secret"))
    assert r.status_code == 200
    assert "removed" in r.json()


def test_admin_config_patch_updates_value(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    r = client.patch(
        "/admin/api/config",
        auth=("admin", "secret"),
        json={"max_upload_size_mb": 99},
    )
    assert r.status_code == 200
    assert r.json()["max_upload_size_mb"] == 99


def test_admin_config_patch_rejects_zero(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    r = client.patch(
        "/admin/api/config",
        auth=("admin", "secret"),
        json={"max_concurrent_jobs": 0},
    )
    assert r.status_code == 422
