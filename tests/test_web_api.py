"""Tests for web/app.py FastAPI endpoints."""
from __future__ import annotations

import io
import sys
import time
import zipfile
from datetime import timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from core.version import APP_VERSION  # noqa: E402
import web.app as app_module  # noqa: E402
from web.app import app, _STORE  # noqa: E402
from web.jobs import JobStatus, JobStore  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    app_module._web_cfg_override.clear()
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app_module._web_cfg_override.clear()


def _make_zip(name: str = "site") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{name}/index.html", "<html><body>test</body></html>")
        zf.writestr(f"{name}/htaccess", "RewriteEngine On\n")
        zf.writestr(f"{name}/sitemap.xml", "<?xml version='1.0'?><urlset></urlset>")
        zf.writestr(f"{name}/404.html", "<html><body>404</body></html>")
        zf.writestr(f"{name}/readme.txt", "Tilda export")
        zf.writestr(f"{name}/robots.txt", "Host: example.com\nSitemap: https://example.com/sitemap.xml\n")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_index_renders_app_version(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert f"<h1>deTilda v{APP_VERSION}</h1>" in r.text
    assert "made with &hearts; by Roman A. Proskurnin" in r.text
    assert f"v{APP_VERSION}" in r.text
    assert 'id="app-version"' not in r.text
    assert "__APP_VERSION__" not in r.text


def test_index_reads_runtime_manifest_version(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "load_manifest", lambda: {"version": "9.9.9"})
    r = client.get("/")
    assert r.status_code == 200
    assert "<h1>deTilda v9.9.9</h1>" in r.text


def test_health_reads_runtime_manifest_version(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "load_manifest", lambda: {"version": "9.9.9"})
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["version"] == "9.9.9"


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
    assert len(body["jobs"]) == 1
    assert body["status"] in ("pending", "running", "done")
    assert body["domain"] == "example.com"


def test_create_jobs_accepts_multiple_files(client: TestClient) -> None:
    r = client.post(
        "/api/jobs",
        files=[
            ("file", ("one.zip", _make_zip("one"), "application/zip")),
            ("file", ("two.zip", _make_zip("two"), "application/zip")),
        ],
        data={"email": "test@example.com"},
    )
    assert r.status_code == 202
    body = r.json()
    assert "jobs" in body
    assert len(body["jobs"]) == 2
    assert {item["filename"] for item in body["jobs"]} == {"one.zip", "two.zip"}
    assert {item["domain"] for item in body["jobs"]} == {"example.com"}


def test_create_job_rejects_non_zip(client: TestClient) -> None:
    r = client.post(
        "/api/jobs",
        files={"file": ("site.tar.gz", b"fake", "application/gzip")},
        data={"email": ""},
    )
    assert r.status_code == 400


def test_create_job_rejects_archive_without_required_tilda_files(client: TestClient) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("site/index.html", "<html></html>")

    r = client.post(
        "/api/jobs",
        files={"file": ("site.zip", buf.getvalue(), "application/zip")},
        data={"email": ""},
    )

    assert r.status_code == 400
    assert "Не найдены обязательные файлы" in r.json()["detail"]
    assert "robots.txt" in r.json()["detail"]


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


def test_download_filename_uses_domain_from_robots(
    client: TestClient,
    monkeypatch,
    tmp_path,
) -> None:
    store = JobStore(persist_dir=tmp_path / "workdir")
    monkeypatch.setattr(app_module, "_STORE", store)
    project = tmp_path / "result"
    project.mkdir()
    (project / "index.html").write_text("<html></html>", encoding="utf-8")
    (project / "robots.txt").write_text(
        "Sitemap: https://www.example.org/sitemap.xml\n",
        encoding="utf-8",
    )
    job = store.create()
    job.status = JobStatus.DONE
    job.result_path = project
    store.update(job)

    r = client.get(f"/api/jobs/{job.id}/download")

    assert r.status_code == 200
    assert 'filename="example.org.zip"' in r.headers["content-disposition"]


# ---------------------------------------------------------------------------
# Admin panel — auth
# ---------------------------------------------------------------------------

def test_admin_page_is_web_login(client: TestClient) -> None:
    r = client.get("/admin")
    assert r.status_code == 200
    assert "Вход в админку" in r.text
    assert "__ADMIN_USER_JSON__" not in r.text


def test_admin_api_requires_auth(client: TestClient) -> None:
    r = client.get("/admin/api/stats")
    assert r.status_code == 401


def test_admin_rejects_wrong_password(client: TestClient, monkeypatch) -> None:
    import os
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    r = client.get("/admin/api/stats", auth=("admin", "wrong"))
    assert r.status_code == 401


def test_admin_accepts_correct_credentials(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    r = client.get("/admin", auth=("admin", "secret"))
    assert r.status_code == 200
    assert "deTilda" in r.text
    assert "__ADMIN_USER_JSON__" not in r.text
    assert 'id="security-panel" class="settings-grid" hidden' in r.text
    assert 'id="security-toggle"' in r.text
    assert 'aria-expanded="false"' in r.text
    assert "<th>Домен</th>" in r.text
    assert "<th>Длительность</th>" in r.text
    assert "<th>Завершена</th>" not in r.text
    assert 'target="_blank"' in r.text


def test_admin_stats_returns_json(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    r = client.get("/admin/api/stats", auth=("admin", "secret"))
    assert r.status_code == 200
    data = r.json()
    assert "total_jobs" in data
    assert "config" in data


def test_admin_jobs_are_paginated(client: TestClient, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    store = JobStore(persist_dir=tmp_path / "workdir")
    monkeypatch.setattr(app_module, "_STORE", store)
    monkeypatch.setattr(app_module, "_LOGS_DIR", tmp_path / "logs")

    first = store.create()
    second = store.create()
    second.domain = "logs.example.com"
    second.finished_at = second.created_at + timedelta(seconds=75)
    store.update(second)
    third = store.create()
    third.domain = "latest.example.com"
    store.update(third)
    log_dir = tmp_path / "logs" / second.id
    log_dir.mkdir(parents=True)
    (log_dir / f"{second.id}_detilda.log").write_text("test log", encoding="utf-8")

    r = client.get("/admin/api/jobs?page=1&page_size=2", auth=("admin", "secret"))

    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["pages"] == 2
    assert len(data["items"]) == 2
    by_id = {item["id"]: item for item in data["items"]}
    assert by_id[third.id]["log_available"] is False
    assert by_id[third.id]["domain"] == "latest.example.com"
    assert by_id[third.id]["domain_url"] == "https://latest.example.com"
    assert by_id[second.id]["log_available"] is True
    assert by_id[second.id]["log_size"] == len("test log")
    assert by_id[second.id]["domain"] == "logs.example.com"
    assert by_id[second.id]["domain_url"] == "https://logs.example.com"
    assert by_id[second.id]["duration_sec"] == 75
    assert first.id not in by_id


def test_admin_job_log_returns_log_content(client: TestClient, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    monkeypatch.setattr(app_module, "_LOGS_DIR", tmp_path / "logs")
    job_id = "job-123"
    log_dir = tmp_path / "logs" / job_id
    log_dir.mkdir(parents=True)
    (log_dir / f"{job_id}_detilda.log").write_text("line 1\nline 2\n", encoding="utf-8")

    r = client.get(f"/admin/api/jobs/{job_id}/log", auth=("admin", "secret"))

    assert r.status_code == 200
    data = r.json()
    assert data["job_id"] == job_id
    assert data["filename"] == f"{job_id}_detilda.log"
    assert data["log"] == "line 1\nline 2\n"


def test_admin_job_log_returns_404_when_missing(client: TestClient, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    monkeypatch.setattr(app_module, "_LOGS_DIR", tmp_path / "logs")

    r = client.get("/admin/api/jobs/missing/log", auth=("admin", "secret"))

    assert r.status_code == 404


def test_admin_cleanup_returns_removed_count(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    r = client.post("/admin/api/cleanup", auth=("admin", "secret"))
    assert r.status_code == 200
    data = r.json()
    assert "removed_jobs" in data
    assert "removed_logs" in data


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


def test_admin_config_patch_updates_required_archive_files(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    r = client.patch(
        "/admin/api/config",
        auth=("admin", "secret"),
        json={"required_archive_files": ["robots.txt", "sitemap.xml"]},
    )
    assert r.status_code == 200
    assert r.json()["required_archive_files"] == ["robots.txt", "sitemap.xml"]


def test_admin_config_patch_rejects_zero(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    r = client.patch(
        "/admin/api/config",
        auth=("admin", "secret"),
        json={"max_concurrent_jobs": 0},
    )
    assert r.status_code == 422


def test_admin_change_password_updates_runtime_and_env_file(
    client: TestClient,
    monkeypatch,
    tmp_path,
) -> None:
    env_file = tmp_path / ".env.admin"
    env_file.write_text("ADMIN_USER=admin\nADMIN_PASSWORD=secret\nOTHER=value\n", encoding="utf-8")
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("ADMIN_ENV_FILE", str(env_file))

    r = client.post(
        "/admin/api/password",
        auth=("admin", "secret"),
        json={"current_password": "secret", "new_password": "new-secret-123"},
    )

    assert r.status_code == 200
    assert r.json()["persisted"] is True
    assert "ADMIN_PASSWORD=new-secret-123" in env_file.read_text(encoding="utf-8")
    assert "OTHER=value" in env_file.read_text(encoding="utf-8")

    old_auth = client.get("/admin/api/stats", auth=("admin", "secret"))
    new_auth = client.get("/admin/api/stats", auth=("admin", "new-secret-123"))

    assert old_auth.status_code == 401
    assert new_auth.status_code == 200


def test_admin_change_password_rejects_wrong_current_password(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")

    r = client.post(
        "/admin/api/password",
        auth=("admin", "secret"),
        json={"current_password": "wrong", "new_password": "new-secret-123"},
    )

    assert r.status_code == 403
