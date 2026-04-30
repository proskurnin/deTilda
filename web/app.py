"""deTilda web application — FastAPI entry point."""
from __future__ import annotations

import concurrent.futures
import os
import secrets
import shutil
import tempfile
import threading
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from core.config_loader import ConfigLoader
from core.packer import pack_result
from core.version import APP_VERSION
from web.jobs import Job, JobStatus, JobStore
from web.worker import run_job

_CONFIG = ConfigLoader()
_STORE = JobStore()
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=5)
_LOGS_DIR = Path(__file__).resolve().parents[1] / "logs"
_WORKDIR = Path(__file__).resolve().parents[1] / "_workdir"

# Per-IP rate limiting state
_rate_map: dict[str, list[float]] = defaultdict(list)
_rate_lock = threading.Lock()

# Admin auth
_http_basic = HTTPBasic()


def _admin_auth(credentials: Annotated[HTTPBasicCredentials, Depends(_http_basic)]) -> str:
    expected_user = os.environ.get("ADMIN_USER", "admin")
    expected_pass = os.environ.get("ADMIN_PASSWORD", "")
    user_ok = secrets.compare_digest(credentials.username.encode(), expected_user.encode())
    pass_ok = secrets.compare_digest(credentials.password.encode(), expected_pass.encode())
    if not expected_pass or not (user_ok and pass_ok):
        raise HTTPException(
            status_code=401,
            detail="Неверные учётные данные",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def _rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    limit = _CONFIG.web().rate_limit_per_minute
    now = time.monotonic()
    with _rate_lock:
        timestamps = [t for t in _rate_map[ip] if now - t < 60.0]
        if len(timestamps) >= limit:
            raise HTTPException(
                status_code=429,
                detail="Слишком много запросов. Повторите через минуту.",
            )
        timestamps.append(now)
        _rate_map[ip] = timestamps


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop = threading.Event()

    def _cleanup_loop() -> None:
        while not stop.wait(timeout=60):
            try:
                ttl = _CONFIG.web().job_ttl_minutes
                expired_ids = _STORE.expire_old(ttl)
                for job_id in expired_ids:
                    shutil.rmtree(_WORKDIR / job_id, ignore_errors=True)
            except Exception:
                pass

    t = threading.Thread(target=_cleanup_loop, daemon=True, name="detilda-cleanup")
    t.start()
    yield
    stop.set()


app = FastAPI(title="deTilda", version=APP_VERSION, lifespan=lifespan)

RateLimited = Annotated[None, Depends(_rate_limit)]


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": APP_VERSION}


@app.post("/api/jobs", status_code=202)
async def create_job(
    _: RateLimited,
    file: UploadFile = File(...),
    email: str = Form(default=""),
) -> dict:
    web_cfg = _CONFIG.web()

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in web_cfg.allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимый тип файла. Разрешено: {web_cfg.allowed_extensions}",
        )

    if _STORE.active_count() >= web_cfg.max_concurrent_jobs:
        raise HTTPException(status_code=429, detail="Слишком много активных задач. Повторите позже.")

    content = await file.read()
    max_bytes = web_cfg.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Файл слишком большой. Максимум: {web_cfg.max_upload_size_mb} МБ",
        )

    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp.write(content)
    tmp.flush()
    tmp.close()

    job = _STORE.create()
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)

    _EXECUTOR.submit(
        run_job,
        job=job,
        store=_STORE,
        upload_path=Path(tmp.name),
        email=email,
        logs_dir=_LOGS_DIR / job.id,
    )

    return {"job_id": job.id, "status": job.status.value}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = _STORE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return job.to_dict()


@app.get("/api/jobs/{job_id}/download")
async def download_result(job_id: str) -> Response:
    job = _STORE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    if job.status != JobStatus.DONE:
        raise HTTPException(status_code=409, detail=f"Задача ещё не завершена: {job.status.value}")
    if not job.result_path or not job.result_path.exists():
        raise HTTPException(status_code=410, detail="Результат недоступен или уже удалён")

    zip_bytes = pack_result(job.result_path)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="detilda_{job_id[:8]}.zip"'},
    )


@app.get("/api/config")
async def get_config() -> dict:
    web_cfg = _CONFIG.web()
    return {
        "max_upload_size_mb": web_cfg.max_upload_size_mb,
        "allowed_extensions": web_cfg.allowed_extensions,
        "max_concurrent_jobs": web_cfg.max_concurrent_jobs,
    }


# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------

AdminUser = Annotated[str, Depends(_admin_auth)]


@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(_: AdminUser) -> str:
    return (Path(__file__).parent / "static" / "admin.html").read_text(encoding="utf-8")


@app.get("/admin/api/jobs")
async def admin_list_jobs(_: AdminUser) -> list:
    return [j.to_dict() for j in _STORE.list_all()]


@app.post("/admin/api/cleanup", status_code=200)
async def admin_cleanup(_: AdminUser) -> dict:
    web_cfg = _CONFIG.web()
    expired_ids = _STORE.expire_old(web_cfg.job_ttl_minutes)
    for job_id in expired_ids:
        shutil.rmtree(_WORKDIR / job_id, ignore_errors=True)
    return {"removed": len(expired_ids)}


@app.get("/admin/api/stats")
async def admin_stats(_: AdminUser) -> dict:
    jobs = _STORE.list_all()
    web_cfg = _CONFIG.web()
    counts: dict[str, int] = {}
    for j in jobs:
        counts[j.status.value] = counts.get(j.status.value, 0) + 1
    return {
        "total_jobs": len(jobs),
        "by_status": counts,
        "version": APP_VERSION,
        "config": {
            "max_upload_size_mb": web_cfg.max_upload_size_mb,
            "max_concurrent_jobs": web_cfg.max_concurrent_jobs,
            "job_ttl_minutes": web_cfg.job_ttl_minutes,
            "rate_limit_per_minute": web_cfg.rate_limit_per_minute,
        },
    }
