"""deTilda web application — FastAPI entry point."""
from __future__ import annotations

import concurrent.futures
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response, StreamingResponse

from core.config_loader import ConfigLoader
from core.packer import pack_result
from core.version import APP_VERSION
from web.jobs import Job, JobStatus, JobStore
from web.worker import run_job

_CONFIG = ConfigLoader()
_STORE = JobStore()
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=5)
_LOGS_DIR = Path(__file__).resolve().parents[1] / "logs"

app = FastAPI(title="deTilda", version=APP_VERSION)


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": APP_VERSION}


@app.post("/api/jobs", status_code=202)
async def create_job(
    file: UploadFile = File(...),
    email: str = Form(default=""),
) -> dict:
    web_cfg = _CONFIG.web()

    # Validate extension
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in web_cfg.allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимый тип файла. Разрешено: {web_cfg.allowed_extensions}",
        )

    # Check concurrency limit
    if _STORE.active_count() >= web_cfg.max_concurrent_jobs:
        raise HTTPException(status_code=429, detail="Слишком много активных задач. Повторите позже.")

    # Read and validate size
    content = await file.read()
    max_bytes = web_cfg.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Файл слишком большой. Максимум: {web_cfg.max_upload_size_mb} МБ",
        )

    # Save upload to a temp file
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp.write(content)
    tmp.flush()
    tmp.close()
    upload_path = Path(tmp.name)

    job = _STORE.create()
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)

    _EXECUTOR.submit(
        run_job,
        job=job,
        store=_STORE,
        upload_path=upload_path,
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


@app.delete("/api/jobs/{job_id}", status_code=204)
async def delete_job(job_id: str) -> None:
    job = _STORE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    # Expire immediately by marking finished_at in the past
    _STORE.expire_old(ttl_minutes=0)
