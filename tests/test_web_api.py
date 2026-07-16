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
from web.app import app  # noqa: E402
from web.auth import UserStore  # noqa: E402
from web.jobs import JobStatus, JobStore  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    app_module._web_cfg_override.clear()
    app_module._rate_map.clear()
    monkeypatch.setattr(app_module, "_STORE", JobStore(persist_dir=tmp_path / "workdir"))
    monkeypatch.setattr(app_module, "_USER_STORE", UserStore(persist_dir=tmp_path / "workdir"))
    monkeypatch.setattr(app_module, "_LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(app_module, "_WORKDIR", tmp_path / "workdir")
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app_module._web_cfg_override.clear()
        app_module._rate_map.clear()


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


def _auth_headers(client: TestClient, email: str = "user@example.com") -> dict[str, str]:
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": "strong-pass-123"},
    )
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['token']}"}


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


def test_index_renders_my_jobs_error_details(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "function jobErrorText(job)" in r.text
    assert "job-error" in r.text
    assert "${escapeHtml(jobErrorText(job))}" in r.text
    assert "state.dataset.status = 'error'" in r.text


def test_index_renders_per_file_upload_settings(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert 'id="email_info_btn"' in r.text
    assert 'id="per_file_enabled"' in r.text
    assert 'name="email_per_file"' in r.text
    assert 'name="ga_measurement_id_per_file"' in r.text
    assert "function domainFromZipName(filename)" in r.text
    assert "`info@${domain}`" in r.text
    assert 'data-info-email-index="${index}"' in r.text
    assert "function renderPerFileSettings()" in r.text
    assert "files.length > 1" in r.text


def test_index_renders_job_details_modal_hooks(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert 'data-job-details="${job.id}"' in r.text
    assert 'data-job-report="${job.id}"' in r.text
    assert "async function openJobDetails(jobId)" in r.text
    assert "async function downloadJobReport(jobId)" in r.text
    assert "function renderJobDetails(job)" in r.text
    assert "`/api/jobs/${jobId}`" in r.text
    assert "`/api/jobs/${jobId}/report`" in r.text
    assert "Этапы pipeline" in r.text
    assert "Предупреждения" in r.text
    assert "Ошибки" in r.text


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

def test_create_job_returns_202(client: TestClient, monkeypatch) -> None:
    class FakeExecutor:
        def submit(self, fn, **kwargs):
            job = kwargs["job"]
            job.status = JobStatus.DONE
            kwargs["store"].update(job)
            kwargs["upload_path"].unlink(missing_ok=True)
            return None

    monkeypatch.setattr(app_module, "_EXECUTOR", FakeExecutor())
    headers = _auth_headers(client)
    r = client.post(
        "/api/jobs",
        files={"file": ("site.zip", _make_zip(), "application/zip")},
        data={"email": "test@example.com", "ga_measurement_id": "G-ABC1234567"},
        headers=headers,
    )
    assert r.status_code == 202
    body = r.json()
    assert "job_id" in body
    assert len(body["jobs"]) == 1
    assert body["status"] in ("pending", "running", "done")
    assert body["domain"] == "example.com"

    job = app_module._STORE.get(body["job_id"])
    assert job is not None
    assert job.filename == "site.zip"
    assert job.email == "test@example.com"
    assert job.ga_measurement_id == "G-ABC1234567"


def test_create_job_requires_registered_user(client: TestClient) -> None:
    r = client.post(
        "/api/jobs",
        files={"file": ("site.zip", _make_zip(), "application/zip")},
        data={"email": "test@example.com"},
    )
    assert r.status_code == 401


def test_create_jobs_accepts_multiple_files(client: TestClient, monkeypatch) -> None:
    class FakeExecutor:
        def submit(self, fn, **kwargs):
            job = kwargs["job"]
            job.status = JobStatus.DONE
            kwargs["store"].update(job)
            kwargs["upload_path"].unlink(missing_ok=True)
            return None

    monkeypatch.setattr(app_module, "_EXECUTOR", FakeExecutor())
    headers = _auth_headers(client)
    r = client.post(
        "/api/jobs",
        files=[
            ("file", ("one.zip", _make_zip("one"), "application/zip")),
            ("file", ("two.zip", _make_zip("two"), "application/zip")),
        ],
        data={"email": "test@example.com"},
        headers=headers,
    )
    assert r.status_code == 202
    body = r.json()
    assert "jobs" in body
    assert len(body["jobs"]) == 2
    assert {item["filename"] for item in body["jobs"]} == {"one.zip", "two.zip"}
    assert {item["domain"] for item in body["jobs"]} == {"example.com"}


def test_create_jobs_accepts_per_file_email_and_ga(client: TestClient, monkeypatch) -> None:
    captured: list[dict] = []

    class FakeExecutor:
        def submit(self, fn, **kwargs):
            captured.append(kwargs)
            job = kwargs["job"]
            job.status = JobStatus.DONE
            kwargs["store"].update(job)
            kwargs["upload_path"].unlink(missing_ok=True)
            return None

    monkeypatch.setattr(app_module, "_EXECUTOR", FakeExecutor())
    headers = _auth_headers(client)
    r = client.post(
        "/api/jobs",
        files=[
            ("file", ("one.zip", _make_zip("one"), "application/zip")),
            ("file", ("two.zip", _make_zip("two"), "application/zip")),
            ("email", (None, "common@example.com")),
            ("ga_measurement_id", (None, "G-COMMON")),
            ("email_per_file", (None, "one@example.com")),
            ("email_per_file", (None, "two@example.com")),
            ("ga_measurement_id_per_file", (None, "g-one123")),
            ("ga_measurement_id_per_file", (None, "g-two456")),
        ],
        headers=headers,
    )

    assert r.status_code == 202
    assert [item["email"] for item in captured] == ["one@example.com", "two@example.com"]
    assert [item["ga_measurement_id"] for item in captured] == ["G-ONE123", "G-TWO456"]


def test_create_jobs_rejects_invalid_per_file_ga(client: TestClient) -> None:
    r = client.post(
        "/api/jobs",
        files=[
            ("file", ("one.zip", _make_zip("one"), "application/zip")),
            ("file", ("two.zip", _make_zip("two"), "application/zip")),
            ("ga_measurement_id_per_file", (None, "G-VALID123")),
            ("ga_measurement_id_per_file", (None, "UA-OLD")),
        ],
        headers=_auth_headers(client),
    )
    assert r.status_code == 422
    assert "Measurement ID" in r.json()["detail"]


def test_create_job_rejects_non_zip(client: TestClient) -> None:
    headers = _auth_headers(client)
    r = client.post(
        "/api/jobs",
        files={"file": ("site.tar.gz", b"fake", "application/gzip")},
        data={"email": ""},
        headers=headers,
    )
    assert r.status_code == 400


def test_create_job_rejects_archive_without_required_tilda_files(client: TestClient) -> None:
    headers = _auth_headers(client)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("site/index.html", "<html></html>")

    r = client.post(
        "/api/jobs",
        files={"file": ("site.zip", buf.getvalue(), "application/zip")},
        data={"email": ""},
        headers=headers,
    )

    assert r.status_code == 400
    assert "Не найдены обязательные файлы" in r.json()["detail"]
    assert "robots.txt" in r.json()["detail"]


def test_create_job_rejects_archive_without_html(client: TestClient) -> None:
    headers = _auth_headers(client)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("site/htaccess", "RewriteEngine On\n")
        zf.writestr("site/sitemap.xml", "<?xml version='1.0'?><urlset></urlset>")
        zf.writestr("site/404.html", "404")
        zf.writestr("site/readme.txt", "Tilda export")
        zf.writestr("site/robots.txt", "Host: example.com\n")

    r = client.post(
        "/api/jobs",
        files={"file": ("site.zip", buf.getvalue(), "application/zip")},
        data={"email": ""},
        headers=headers,
    )

    assert r.status_code == 400
    assert "HTML-страницы" in r.json()["detail"]


def test_create_job_rejects_invalid_ga_measurement_id(client: TestClient) -> None:
    r = client.post(
        "/api/jobs",
        files={"file": ("site.zip", _make_zip(), "application/zip")},
        data={"ga_measurement_id": "UA-OLD"},
        headers=_auth_headers(client),
    )
    assert r.status_code == 422
    assert "Measurement ID" in r.json()["detail"]


def test_create_job_rejects_oversized_file(client: TestClient, monkeypatch) -> None:
    from web import app as app_module
    from core.schemas import WebConfig

    headers = _auth_headers(client)
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
            headers=headers,
        )
        assert r.status_code == 413
    finally:
        app_module._CONFIG.web = original_web


# ---------------------------------------------------------------------------
# GET /api/jobs/{id}
# ---------------------------------------------------------------------------

def test_get_job_not_found(client: TestClient) -> None:
    r = client.get("/api/jobs/nonexistent-id", headers=_auth_headers(client))
    assert r.status_code == 404


def test_get_job_returns_status(client: TestClient) -> None:
    headers = _auth_headers(client)
    create = client.post(
        "/api/jobs",
        files={"file": ("site.zip", _make_zip(), "application/zip")},
        data={"email": ""},
        headers=headers,
    )
    assert create.status_code == 202
    job_id = create.json()["job_id"]

    r = client.get(f"/api/jobs/{job_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["id"] == job_id
    assert "status" in r.json()


def test_users_only_see_their_own_jobs(client: TestClient) -> None:
    first_headers = _auth_headers(client, "first@example.com")
    second_headers = _auth_headers(client, "second@example.com")

    create = client.post(
        "/api/jobs",
        files={"file": ("site.zip", _make_zip(), "application/zip")},
        data={"email": ""},
        headers=first_headers,
    )
    assert create.status_code == 202
    job_id = create.json()["job_id"]

    hidden = client.get(f"/api/jobs/{job_id}", headers=second_headers)
    assert hidden.status_code == 404

    first_jobs = client.get("/api/jobs", headers=first_headers)
    second_jobs = client.get("/api/jobs", headers=second_headers)
    assert job_id in {item["id"] for item in first_jobs.json()["items"]}
    assert job_id not in {item["id"] for item in second_jobs.json()["items"]}


# ---------------------------------------------------------------------------
# GET /api/jobs/{id}/download — job not done
# ---------------------------------------------------------------------------

def test_download_not_done_returns_409(client: TestClient) -> None:
    """Download before job finishes returns 409."""
    headers = _auth_headers(client)
    user = app_module._USER_STORE.get_user_by_token(headers["Authorization"].split(" ", 1)[1])
    assert user is not None
    job = app_module._STORE.create(owner_user_id=user.id)
    # job.status stays PENDING
    r = client.get(f"/api/jobs/{job.id}/download", headers=headers)
    assert r.status_code == 409


def test_download_filename_uses_domain_from_robots(
    client: TestClient,
    monkeypatch,
    tmp_path,
) -> None:
    store = JobStore(persist_dir=tmp_path / "workdir")
    user_store = UserStore(persist_dir=tmp_path / "workdir")
    monkeypatch.setattr(app_module, "_STORE", store)
    monkeypatch.setattr(app_module, "_USER_STORE", user_store)
    headers = _auth_headers(client, "download@example.com")
    user = user_store.get_user_by_token(headers["Authorization"].split(" ", 1)[1])
    assert user is not None
    project = tmp_path / "result"
    project.mkdir()
    (project / "index.html").write_text("<html></html>", encoding="utf-8")
    (project / "robots.txt").write_text(
        "Sitemap: https://www.example.org/sitemap.xml\n",
        encoding="utf-8",
    )
    job = store.create(owner_user_id=user.id)
    job.status = JobStatus.DONE
    job.result_path = project
    store.update(job)

    r = client.get(f"/api/jobs/{job.id}/download", headers=headers)

    assert r.status_code == 200
    assert 'filename="example.org.zip"' in r.headers["content-disposition"]


def test_download_report_returns_processing_report(client: TestClient, tmp_path) -> None:
    headers = _auth_headers(client, "report@example.com")
    user = app_module._USER_STORE.get_user_by_token(headers["Authorization"].split(" ", 1)[1])
    assert user is not None
    job = app_module._STORE.create(owner_user_id=user.id)
    job.domain = "example.com"
    app_module._STORE.update(job)
    report_dir = app_module._LOGS_DIR / job.id
    report_dir.mkdir(parents=True)
    (report_dir / "processing_report.json").write_text('{"job_id":"%s"}' % job.id, encoding="utf-8")

    r = client.get(f"/api/jobs/{job.id}/report", headers=headers)

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["job_id"] == job.id
    assert 'filename="example.com_processing_report.json"' in r.headers["content-disposition"]


def test_download_report_hidden_from_other_users(client: TestClient) -> None:
    first_headers = _auth_headers(client, "report-owner@example.com")
    second_headers = _auth_headers(client, "report-other@example.com")
    user = app_module._USER_STORE.get_user_by_token(first_headers["Authorization"].split(" ", 1)[1])
    assert user is not None
    job = app_module._STORE.create(owner_user_id=user.id)
    app_module._STORE.update(job)
    report_dir = app_module._LOGS_DIR / job.id
    report_dir.mkdir(parents=True)
    (report_dir / "processing_report.json").write_text("{}", encoding="utf-8")

    r = client.get(f"/api/jobs/{job.id}/report", headers=second_headers)

    assert r.status_code == 404


def test_download_report_returns_410_when_missing(client: TestClient) -> None:
    headers = _auth_headers(client, "missing-report@example.com")
    user = app_module._USER_STORE.get_user_by_token(headers["Authorization"].split(" ", 1)[1])
    assert user is not None
    job = app_module._STORE.create(owner_user_id=user.id)

    r = client.get(f"/api/jobs/{job.id}/report", headers=headers)

    assert r.status_code == 410
    assert "Отчёт" in r.json()["detail"]


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
    headers = _auth_headers(client)
