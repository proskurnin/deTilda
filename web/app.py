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
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
from web.auth import User, UserStore
from web.jobs import JobStatus, JobStore
from web.worker import run_job

_CONFIG = ConfigLoader()
_LOGS_DIR = Path(__file__).resolve().parents[1] / "logs"
_WORKDIR = Path(__file__).resolve().parents[1] / "_workdir"
_STORE = JobStore(persist_dir=_WORKDIR)
_USER_STORE = UserStore(persist_dir=_WORKDIR)
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
_TILDA_EXPORT_MARKERS_RE = re.compile(
    r'data-aida-export=["\']yes["\']|data-tilda-project-id',
    re.IGNORECASE,
)
_HTML_ASSET_REF_RE = re.compile(
    r"""(?:src|href|data-original|data-lazy)=["'](?P<link>[^"']+)["']""",
    re.IGNORECASE,
)
_GA_MEASUREMENT_ID_RE = re.compile(r"^G-[A-Z0-9]+$", re.IGNORECASE)


@dataclass
class ZipValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    def to_job_details(self) -> dict:
        items: list[str] = []
        items.extend(f"Ошибка: {item}" for item in self.errors)
        items.extend(f"Предупреждение: {item}" for item in self.warnings)
        items.extend(self.info)
        return {
            "errors": self.errors,
            "warnings": self.warnings,
            "items": items or ["Архив прошёл базовую валидацию."],
        }


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


def _job_duration_seconds(job) -> int:
    start = job.created_at
    end = job.finished_at or datetime.now(timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return max(0, int((end - start).total_seconds()))


def _admin_job_dict(job) -> dict:
    data = job.to_admin_dict()
    log_path = _find_job_log(job.id)
    domain = data.get("domain")
    if not domain and job.result_path:
        domain = _domain_from_robots(job.result_path)
    data["domain"] = domain
    data["domain_url"] = f"https://{domain}" if domain else None
    data["duration_sec"] = _job_duration_seconds(job)
    data["log_available"] = bool(log_path)
    data["log_size"] = log_path.stat().st_size if log_path else 0
    return data


def _required_file_aliases(filename: str) -> set[str]:
    normalized = filename.strip().replace("\\", "/").lstrip("/").lower()
    aliases = {normalized}
    if normalized == "htaccess":
        aliases.add(".htaccess")
    elif normalized == ".htaccess":
        aliases.add("htaccess")
    return aliases


def _strip_archive_root(names: list[str]) -> tuple[list[tuple[str, str]], set[str], set[str]]:
    files = [name for name in names if name and not name.endswith("/")]
    first_parts = {name.split("/", 1)[0] for name in files if "/" in name}
    has_root_files = any("/" not in name for name in files)
    strip_root = len(first_parts) == 1 and not has_root_files
    root = next(iter(first_parts)) if strip_root else ""

    pairs: list[tuple[str, str]] = []
    rootless_files: set[str] = set()
    rootless_dirs: set[str] = set()
    for name in files:
        normalized = name.replace("\\", "/").lstrip("/")
        rootless = normalized
        if strip_root and rootless.startswith(root + "/"):
            rootless = rootless[len(root) + 1:]
        lowered = rootless.lower()
        pairs.append((name, rootless))
        rootless_files.add(lowered)
        parts = lowered.split("/")
        for idx in range(1, len(parts)):
            rootless_dirs.add("/".join(parts[:idx]))
    return pairs, rootless_files, rootless_dirs


def _is_local_archive_ref(link: str) -> bool:
    link = link.strip()
    if not link or link.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return False
    split = re.split(r"[?#]", link, maxsplit=1)[0]
    if not split or split.startswith(("http://", "https://", "//")):
        return False
    return "/" in split.lstrip("./")


def _top_level_dir_from_ref(link: str) -> str | None:
    split = re.split(r"[?#]", link.strip(), maxsplit=1)[0]
    split = split.replace("\\", "/").lstrip("/")
    while split.startswith("./"):
        split = split[2:]
    if split.startswith("../"):
        return None
    parts = [part for part in split.split("/") if part and part != "."]
    if len(parts) < 2:
        return None
    return parts[0].lower()


def _validate_tilda_export_zip(content: bytes, required_files: list[str]) -> ZipValidationResult:
    result = ZipValidationResult()
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            entries = zf.namelist()
            pairs, rootless, rootless_dirs = _strip_archive_root(entries)
            html_entries = [
                (original, rootless_name)
                for original, rootless_name in pairs
                if rootless_name.lower().endswith((".html", ".htm"))
            ]

            missing = [
                filename for filename in required_files
                if not (_required_file_aliases(filename) & rootless)
            ]
            if missing:
                result.errors.append("Не найдены обязательные файлы: " + ", ".join(missing))

            if not html_entries:
                result.errors.append("В архиве не найдены HTML-страницы.")
            else:
                result.info.append(f"HTML-страниц найдено: {len(html_entries)}")
                content_pages = [
                    rootless_name for _original, rootless_name in html_entries
                    if Path(rootless_name).name.lower() != "404.html"
                ]
                if not content_pages:
                    result.errors.append("В архиве не найдены HTML-страницы сайта кроме 404.html.")

            marker_pages = 0
            referenced_dirs: set[str] = set()
            for original, rootless_name in html_entries:
                try:
                    html = zf.read(original).decode("utf-8", errors="replace")
                except (OSError, UnicodeError):
                    continue
                if _TILDA_EXPORT_MARKERS_RE.search(html):
                    marker_pages += 1
                for match in _HTML_ASSET_REF_RE.finditer(html):
                    link = match.group("link")
                    if not _is_local_archive_ref(link):
                        continue
                    top_dir = _top_level_dir_from_ref(link)
                    if top_dir:
                        referenced_dirs.add(top_dir)

            if marker_pages:
                result.info.append(f"Tilda/Aida export markers найдены на страницах: {marker_pages}")
            elif html_entries:
                result.warnings.append(
                    "В HTML не найдены маркеры data-aida-export=\"yes\" или data-tilda-project-id."
                )

            missing_dirs = sorted(
                folder for folder in referenced_dirs
                if folder not in rootless_dirs and folder not in rootless
            )
            if missing_dirs:
                result.warnings.append(
                    "HTML ссылается на отсутствующие asset-папки: " + ", ".join(missing_dirs)
                )
            elif referenced_dirs:
                result.info.append(
                    "Asset-папки из HTML найдены: " + ", ".join(sorted(referenced_dirs))
                )
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Файл повреждён или не является ZIP-архивом.")

    if result.errors:
        raise HTTPException(
            status_code=400,
            detail=(
                "Архив не похож на полный экспорт Tilda. "
                + " ".join(result.errors)
            ),
        )
    return result


def _read_zip_text(content: bytes, filename: str) -> str | None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            files = [name for name in zf.namelist() if name and not name.endswith("/")]
            first_parts = {name.split("/", 1)[0] for name in files if "/" in name}
            has_root_files = any("/" not in name for name in files)
            strip_root = len(first_parts) == 1 and not has_root_files
            root = next(iter(first_parts)) if strip_root else ""
            target = filename.lower()
            for name in files:
                normalized = name.replace("\\", "/").lstrip("/")
                rootless = normalized
                if strip_root and rootless.startswith(root + "/"):
                    rootless = rootless[len(root) + 1:]
                if rootless.lower() == target:
                    return zf.read(name).decode("utf-8", errors="replace")
    except (OSError, UnicodeError, zipfile.BadZipFile):
        return None
    return None


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


def _domain_from_robots_text(text: str) -> str | None:
    sitemap_domain = None
    for line in text.splitlines():
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


def _domain_from_zip_content(content: bytes) -> str | None:
    robots = _read_zip_text(content, "robots.txt")
    if not robots:
        return None
    return _domain_from_robots_text(robots)


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


def _extract_bearer_token(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Требуется вход в аккаунт")
    return token.strip()


def _current_user(request: Request) -> User:
    token = _extract_bearer_token(request)
    user = _USER_STORE.get_user_by_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Сессия недействительна")
    return user


CurrentUser = Annotated[User, Depends(_current_user)]


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


@app.post("/api/auth/register", status_code=201)
async def register_user(body: dict = Body(...)) -> dict:
    email = str(body.get("email", ""))
    password = str(body.get("password", ""))
    try:
        user = _USER_STORE.create_user(email=email, password=password)
    except ValueError as exc:
        code = str(exc)
        messages = {
            "invalid_email": "Введите корректный email.",
            "weak_password": "Пароль должен быть не короче 8 символов.",
            "email_exists": "Пользователь с таким email уже зарегистрирован.",
        }
        status = 409 if code == "email_exists" else 422
        raise HTTPException(status_code=status, detail=messages.get(code, "Не удалось зарегистрировать пользователя."))
    token = _USER_STORE.create_session(user.id)
    return {"token": token, "user": user.to_dict()}


@app.post("/api/auth/login")
async def login_user(body: dict = Body(...)) -> dict:
    email = str(body.get("email", ""))
    password = str(body.get("password", ""))
    user = _USER_STORE.authenticate(email=email, password=password)
    if user is None:
        raise HTTPException(status_code=401, detail="Неверный email или пароль.")
    token = _USER_STORE.create_session(user.id)
    return {"token": token, "user": user.to_dict()}


@app.get("/api/me")
async def get_me(user: CurrentUser) -> dict:
    return {"user": user.to_dict()}


@app.post("/api/auth/logout")
async def logout_user(request: Request, user: CurrentUser) -> dict:
    _USER_STORE.revoke_session(_extract_bearer_token(request))
    return {"ok": True, "user_id": user.id}


@app.post("/api/jobs", status_code=202)
async def create_job(
    _: RateLimited,
    user: CurrentUser,
    file: list[UploadFile] = File(...),
    email: str = Form(default=""),
    ga_measurement_id: str = Form(default=""),
) -> dict:
    web_cfg = _get_web_cfg()
    uploads = file
    ga_measurement_id = ga_measurement_id.strip().upper()
    if ga_measurement_id and not _GA_MEASUREMENT_ID_RE.fullmatch(ga_measurement_id):
        raise HTTPException(status_code=422, detail="Google Analytics Measurement ID должен иметь формат G-XXXXXXXX.")

    if not uploads:
        raise HTTPException(status_code=400, detail="Файлы не выбраны.")
    if _STORE.active_count() + len(uploads) > web_cfg.max_concurrent_jobs:
        raise HTTPException(status_code=429, detail="Слишком много активных задач. Повторите позже.")

    max_bytes = web_cfg.max_upload_size_mb * 1024 * 1024
    prepared: list[tuple[UploadFile, Path, str | None, dict]] = []
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
            validation = _validate_tilda_export_zip(content, web_cfg.required_archive_files)
            domain = _domain_from_zip_content(content)

            tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
            tmp.write(content)
            tmp.flush()
            tmp.close()
            prepared.append((upload, Path(tmp.name), domain, validation.to_job_details()))

        _LOGS_DIR.mkdir(parents=True, exist_ok=True)
        created: list[dict] = []
        for upload, tmp_path, domain, validation_details in prepared:
            job = _STORE.create(owner_user_id=user.id)
            job.domain = domain
            job.validation_details = validation_details
            _STORE.update(job)
            _EXECUTOR.submit(
                run_job,
                job=job,
                store=_STORE,
                upload_path=tmp_path,
                email=email,
                logs_dir=_LOGS_DIR / job.id,
                ga_measurement_id=ga_measurement_id,
                validation_details=validation_details,
            )
            created.append({
                "job_id": job.id,
                "status": job.status.value,
                "filename": upload.filename or "",
                "domain": domain,
            })
    except HTTPException:
        for _, tmp_path, _, _ in prepared:
            tmp_path.unlink(missing_ok=True)
        raise

    response: dict = {"jobs": created}
    if len(created) == 1:
        response.update(created[0])
    return response


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str, user: CurrentUser) -> dict:
    job = _STORE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    if job.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return job.to_dict()


@app.get("/api/jobs/{job_id}/download")
async def download_result(job_id: str, user: CurrentUser) -> Response:
    job = _STORE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    if job.owner_user_id != user.id:
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


@app.get("/api/jobs")
async def list_my_jobs(user: CurrentUser) -> dict:
    return {
        "items": [job.to_dict() for job in _STORE.list_for_user(user.id)],
    }


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
