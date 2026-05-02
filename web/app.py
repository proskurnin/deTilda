"""deTilda web application — FastAPI entry point."""
from __future__ import annotations

import concurrent.futures
import io
import json
import os
import re
import secrets
import shutil
import tempfile
import threading
import time
import zipfile
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from core.config_loader import ConfigLoader
from core.packer import pack_result
from core.schemas import WebConfig
from core.utils import load_manifest
from core.version import APP_VERSION
from web.jobs import JobStatus, JobStore
from web.worker import run_job

_CONFIG = ConfigLoader()
_LOGS_DIR = Path(__file__).resolve().parents[1] / "logs"
_WORKDIR = Path(__file__).resolve().parents[1] / "_workdir"
_STORE = JobStore(persist_dir=_WORKDIR)
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=5)

# Per-IP rate limiting
_rate_map: dict[str, list[float]] = defaultdict(list)
_rate_lock = threading.Lock()

# In-memory config overrides (reset on restart)
_web_cfg_override: dict = {}
_web_cfg_lock = threading.Lock()

# Admin auth
_http_basic = HTTPBasic()
_admin_password_lock = threading.Lock()

_CFG_INT_FIELDS = frozenset({
    "max_upload_size_mb", "processing_timeout_sec",
    "max_concurrent_jobs", "job_ttl_minutes", "log_ttl_days", "rate_limit_per_minute",
})
_CFG_LIST_FIELDS = frozenset({"required_archive_files"})
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _get_runtime_version() -> str:
    manifest = load_manifest()
    return str(manifest.get("version", APP_VERSION))


def _get_web_cfg() -> WebConfig:
    base = _CONFIG.web()
    with _web_cfg_lock:
        override = dict(_web_cfg_override)
    if not override:
        return base
    fields = ("max_upload_size_mb", "processing_timeout_sec", "allowed_extensions",
              "required_archive_files", "max_concurrent_jobs", "job_ttl_minutes",
              "log_ttl_days", "rate_limit_per_minute")
    merged = {f: getattr(base, f) for f in fields}
    merged.update(override)
    return WebConfig(**merged)


def _cleanup_old_logs(logs_dir: Path, ttl_days: int) -> int:
    """Delete log subdirectories older than ttl_days (by mtime). Returns count removed."""
    if not logs_dir.exists():
        return 0
    cutoff = time.time() - ttl_days * 86400
    removed = 0
    for entry in logs_dir.iterdir():
        if entry.is_dir():
            try:
                if entry.stat().st_mtime < cutoff:
                    shutil.rmtree(entry, ignore_errors=True)
                    removed += 1
            except OSError:
                pass
    return removed


def _find_job_log(job_id: str) -> Path | None:
    """Return the main deTilda log for a web job, if it is still available."""
    log_dir = _LOGS_DIR / job_id
    if log_dir.is_dir():
        candidates = sorted(log_dir.glob("*_detilda.log"))
        if candidates:
            return candidates[0]

    legacy_log = _LOGS_DIR / f"{job_id}_detilda.log"
    if legacy_log.is_file():
        return legacy_log
    return None


def _admin_job_dict(job) -> dict:
    data = job.to_admin_dict()
    log_path = _find_job_log(job.id)
    data["log_available"] = bool(log_path)
    data["log_size"] = log_path.stat().st_size if log_path else 0
    return data


def _archive_rootless_names(names: list[str]) -> set[str]:
    files = [name for name in names if name and not name.endswith("/")]
    first_parts = {name.split("/", 1)[0] for name in files if "/" in name}
    has_root_files = any("/" not in name for name in files)
    strip_root = len(first_parts) == 1 and not has_root_files
    root = next(iter(first_parts)) if strip_root else ""

    rootless: set[str] = set()
    for name in files:
        normalized = name.replace("\\", "/").lstrip("/")
        if strip_root and normalized.startswith(root + "/"):
            normalized = normalized[len(root) + 1:]
        rootless.add(normalized.lower())
    return rootless


def _required_file_aliases(filename: str) -> set[str]:
    normalized = filename.strip().replace("\\", "/").lstrip("/").lower()
    aliases = {normalized}
    if normalized == "htaccess":
        aliases.add(".htaccess")
    elif normalized == ".htaccess":
        aliases.add("htaccess")
    return aliases


def _validate_tilda_export_zip(content: bytes, required_files: list[str]) -> None:
    if not required_files:
        return
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            rootless = _archive_rootless_names(zf.namelist())
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Файл повреждён или не является ZIP-архивом.")

    missing = [
        filename for filename in required_files
        if not (_required_file_aliases(filename) & rootless)
    ]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=(
                "Архив не похож на полный экспорт Tilda. "
                "Не найдены обязательные файлы: " + ", ".join(missing)
            ),
        )


def _safe_zip_stem(value: str) -> str:
    stem = re.sub(r"^https?://", "", value.strip(), flags=re.IGNORECASE)
    stem = stem.split("/", 1)[0].split(":", 1)[0].lower()
    stem = stem.removeprefix("www.")
    stem = re.sub(r"[^a-z0-9._-]+", "-", stem).strip(".-_")
    return stem or "detilda"


def _domain_from_robots(project_root: Path) -> str | None:
    robots = project_root / "robots.txt"
    if not robots.is_file():
        return None
    try:
        lines = robots.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None

    sitemap_domain = None
    for line in lines:
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip().lower()
        value = value.strip()
        if key == "host" and value:
            return _safe_zip_stem(value)
        if key == "sitemap" and value and sitemap_domain is None:
            sitemap_domain = _safe_zip_stem(value)
    return sitemap_domain


def _download_filename(job) -> str:
    if job.result_path:
        domain = _domain_from_robots(job.result_path)
        if domain:
            return f"{domain}.zip"
    return f"detilda_{job.id[:8]}.zip"


def _admin_auth(
    credentials: Annotated[HTTPBasicCredentials, Depends(_http_basic)],
) -> HTTPBasicCredentials:
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
    return credentials


def _quote_env_value(value: str) -> str:
    if value and re.fullmatch(r"[A-Za-z0-9_@%+=:,./-]+", value):
        return value
    escaped = (
        value
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("`", "\\`")
    )
    return f'"{escaped}"'


def _write_env_value(env_path: Path, key: str, value: str) -> None:
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    rendered = f"{key}={_quote_env_value(value)}"
    replaced = False
    next_lines: list[str] = []
    for line in lines:
        if _ENV_KEY_RE.match(line) and line.split("=", 1)[0] == key:
            next_lines.append(rendered)
            replaced = True
        else:
            next_lines.append(line)
    if not replaced:
        next_lines.append(rendered)
    env_path.write_text("\n".join(next_lines) + "\n", encoding="utf-8")


def _set_admin_password(new_password: str) -> bool:
    """Update the runtime admin password and persist it when ADMIN_ENV_FILE is configured."""
    env_file = os.environ.get("ADMIN_ENV_FILE", "")
    with _admin_password_lock:
        os.environ["ADMIN_PASSWORD"] = new_password
        if not env_file:
            return False
        _write_env_value(Path(env_file), "ADMIN_PASSWORD", new_password)
        return True


def _rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    limit = _get_web_cfg().rate_limit_per_minute
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
    _WORKDIR.mkdir(parents=True, exist_ok=True)
    _STORE.restore()

    stop = threading.Event()

    def _cleanup_loop() -> None:
        while not stop.wait(timeout=60):
            try:
                cfg = _get_web_cfg()
                expired_ids = _STORE.expire_old(cfg.job_ttl_minutes)
                for job_id in expired_ids:
                    shutil.rmtree(_WORKDIR / job_id, ignore_errors=True)
                _cleanup_old_logs(_LOGS_DIR, cfg.log_ttl_days)
            except Exception:
                pass

    t = threading.Thread(target=_cleanup_loop, daemon=True, name="detilda-cleanup")
    t.start()
    yield
    stop.set()


app = FastAPI(title="deTilda", version=APP_VERSION, lifespan=lifespan)

RateLimited = Annotated[None, Depends(_rate_limit)]
AdminAuth = Annotated[HTTPBasicCredentials, Depends(_admin_auth)]


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    html = (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")
    return html.replace("__APP_VERSION__", _get_runtime_version())


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": _get_runtime_version()}


@app.post("/api/jobs", status_code=202)
async def create_job(
    _: RateLimited,
    file: list[UploadFile] = File(...),
    email: str = Form(default=""),
) -> dict:
    web_cfg = _get_web_cfg()
    uploads = file

    if not uploads:
        raise HTTPException(status_code=400, detail="Файлы не выбраны.")
    if _STORE.active_count() + len(uploads) > web_cfg.max_concurrent_jobs:
        raise HTTPException(status_code=429, detail="Слишком много активных задач. Повторите позже.")

    max_bytes = web_cfg.max_upload_size_mb * 1024 * 1024
    prepared: list[tuple[UploadFile, Path]] = []
    try:
        for upload in uploads:
            suffix = Path(upload.filename or "").suffix.lower()
            if suffix not in web_cfg.allowed_extensions:
                raise HTTPException(
                    status_code=400,
                    detail=f"{upload.filename}: недопустимый тип файла. Разрешено: {web_cfg.allowed_extensions}",
                )

            content = await upload.read()
            if len(content) > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"{upload.filename}: файл слишком большой. Максимум: {web_cfg.max_upload_size_mb} МБ",
                )
            _validate_tilda_export_zip(content, web_cfg.required_archive_files)

            tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
            tmp.write(content)
            tmp.flush()
            tmp.close()
            prepared.append((upload, Path(tmp.name)))

        _LOGS_DIR.mkdir(parents=True, exist_ok=True)
        created: list[dict] = []
        for upload, tmp_path in prepared:
            job = _STORE.create()
            _EXECUTOR.submit(
                run_job,
                job=job,
                store=_STORE,
                upload_path=tmp_path,
                email=email,
                logs_dir=_LOGS_DIR / job.id,
            )
            created.append({
                "job_id": job.id,
                "status": job.status.value,
                "filename": upload.filename or "",
            })
    except HTTPException:
        for _, tmp_path in prepared:
            tmp_path.unlink(missing_ok=True)
        raise

    response: dict = {"jobs": created}
    if len(created) == 1:
        response.update(created[0])
    return response


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
        headers={"Content-Disposition": f'attachment; filename="{_download_filename(job)}"'},
    )


@app.get("/api/config")
async def get_config() -> dict:
    web_cfg = _get_web_cfg()
    return {
        "max_upload_size_mb": web_cfg.max_upload_size_mb,
        "allowed_extensions": web_cfg.allowed_extensions,
        "required_archive_files": web_cfg.required_archive_files,
        "max_concurrent_jobs": web_cfg.max_concurrent_jobs,
    }


# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel() -> str:
    html = (Path(__file__).parent / "static" / "admin.html").read_text(encoding="utf-8")
    return html.replace("__ADMIN_USER_JSON__", json.dumps(os.environ.get("ADMIN_USER", "admin")))


@app.get("/admin/api/jobs")
async def admin_list_jobs(
    _: AdminAuth,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    jobs = _STORE.list_all()
    total = len(jobs)
    pages = max((total + page_size - 1) // page_size, 1)
    page = min(page, pages)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "items": [_admin_job_dict(j) for j in jobs[start:end]],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }


@app.get("/admin/api/jobs/{job_id}/log")
async def admin_job_log(job_id: str, _: AdminAuth) -> dict:
    log_path = _find_job_log(job_id)
    if log_path is None:
        raise HTTPException(status_code=404, detail="Лог задачи не найден")
    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        raise HTTPException(status_code=410, detail="Лог задачи недоступен")
    return {
        "job_id": job_id,
        "filename": log_path.name,
        "log": content,
    }


@app.get("/admin/api/stats")
async def admin_stats(_: AdminAuth) -> dict:
    jobs = _STORE.list_all()
    web_cfg = _get_web_cfg()
    counts: dict[str, int] = {}
    for j in jobs:
        counts[j.status.value] = counts.get(j.status.value, 0) + 1
    return {
        "total_jobs": len(jobs),
        "by_status": counts,
        "version": APP_VERSION,
        "config": {
            "max_upload_size_mb": web_cfg.max_upload_size_mb,
            "processing_timeout_sec": web_cfg.processing_timeout_sec,
            "required_archive_files": web_cfg.required_archive_files,
            "max_concurrent_jobs": web_cfg.max_concurrent_jobs,
            "job_ttl_minutes": web_cfg.job_ttl_minutes,
            "log_ttl_days": web_cfg.log_ttl_days,
            "rate_limit_per_minute": web_cfg.rate_limit_per_minute,
        },
    }


@app.patch("/admin/api/config")
async def admin_update_config(
    _: AdminAuth,
    body: dict = Body(...),
) -> dict:
    updates: dict = {}
    for key, val in body.items():
        if key in _CFG_INT_FIELDS:
            try:
                v = int(val)
                if v <= 0:
                    raise HTTPException(status_code=422, detail=f"{key} должен быть > 0")
                updates[key] = v
            except (ValueError, TypeError):
                raise HTTPException(status_code=422, detail=f"{key}: ожидается целое число")
        elif key in _CFG_LIST_FIELDS:
            if isinstance(val, str):
                items = [line.strip() for line in val.splitlines()]
            elif isinstance(val, list):
                items = [str(item).strip() for item in val]
            else:
                raise HTTPException(status_code=422, detail=f"{key}: ожидается список строк")
            updates[key] = [item for item in items if item]
    with _web_cfg_lock:
        _web_cfg_override.update(updates)
    cfg = _get_web_cfg()
    return {
        "max_upload_size_mb": cfg.max_upload_size_mb,
        "processing_timeout_sec": cfg.processing_timeout_sec,
        "required_archive_files": cfg.required_archive_files,
        "max_concurrent_jobs": cfg.max_concurrent_jobs,
        "job_ttl_minutes": cfg.job_ttl_minutes,
        "rate_limit_per_minute": cfg.rate_limit_per_minute,
    }


@app.post("/admin/api/password")
async def admin_change_password(
    creds: AdminAuth,
    body: dict = Body(...),
) -> dict:
    current_password = str(body.get("current_password", ""))
    new_password = str(body.get("new_password", ""))
    if not secrets.compare_digest(current_password.encode(), creds.password.encode()):
        raise HTTPException(status_code=403, detail="Текущий пароль указан неверно")
    if len(new_password) < 8:
        raise HTTPException(status_code=422, detail="Новый пароль должен быть не короче 8 символов")
    if "\n" in new_password or "\r" in new_password:
        raise HTTPException(status_code=422, detail="Новый пароль не должен содержать переносы строк")
    if secrets.compare_digest(new_password.encode(), current_password.encode()):
        raise HTTPException(status_code=422, detail="Новый пароль должен отличаться от текущего")
    try:
        persisted = _set_admin_password(new_password)
    except OSError:
        raise HTTPException(status_code=500, detail="Не удалось сохранить пароль в env-файл")
    return {
        "ok": True,
        "username": creds.username,
        "persisted": persisted,
    }


@app.post("/admin/api/cleanup", status_code=200)
async def admin_cleanup(_: AdminAuth) -> dict:
    cfg = _get_web_cfg()
    expired_ids = _STORE.expire_old(cfg.job_ttl_minutes)
    for job_id in expired_ids:
        shutil.rmtree(_WORKDIR / job_id, ignore_errors=True)
    removed_logs = _cleanup_old_logs(_LOGS_DIR, cfg.log_ttl_days)
    return {"removed_jobs": len(expired_ids), "removed_logs": removed_logs}
