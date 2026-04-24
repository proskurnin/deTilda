"""Reusable helper utilities for the deTilda toolkit."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Sequence

from core import logger

__all__ = [
    "ensure_dir",
    "get_elapsed_time",
    "list_files_recursive",
    "load_manifest",
    "relpath",
    "safe_copy",
    "safe_delete",
    "safe_read",
    "safe_write",
]


def _to_path(path: Path | str) -> Path:
    return path if isinstance(path, Path) else Path(path)


def safe_read(path: Path | str) -> str:
    path_obj = _to_path(path)
    if not path_obj.exists():
        raise FileNotFoundError(f"Файл не найден: {path_obj}")
    try:
        return path_obj.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path_obj.read_text(encoding="utf-8-sig")


def safe_write(path: Path | str, content: str) -> None:
    path_obj = _to_path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    path_obj.write_text(content, encoding="utf-8", newline="\n")


def safe_copy(src: Path | str, dst: Path | str) -> None:
    src_path = _to_path(src)
    dst_path = _to_path(dst)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, dst_path)
    logger.info(f"📄 Копия создана: {dst_path.name}")


def safe_delete(path: Path | str) -> None:
    path_obj = _to_path(path)
    if path_obj.exists():
        path_obj.unlink()
        logger.info(f"🗑 Удалён файл: {path_obj}")


def relpath(path: Path | str, base: Path | str) -> str:
    path_obj = _to_path(path).resolve()
    base_obj = _to_path(base).resolve()
    try:
        return str(path_obj.relative_to(base_obj)).replace("\\", "/")
    except ValueError:
        return path_obj.name


def ensure_dir(path: Path | str) -> Path:
    path_obj = _to_path(path)
    path_obj.mkdir(parents=True, exist_ok=True)
    return path_obj


def list_files_recursive(base_dir: Path | str, extensions: Sequence[str] | None = None) -> list[Path]:
    base_path = _to_path(base_dir)
    exts = {ext.lower() for ext in extensions or ()}
    result: list[Path] = []
    for file_path in base_path.rglob("*"):
        if not file_path.is_file():
            continue
        if exts and file_path.suffix.lower() not in exts:
            continue
        result.append(file_path)
    return result


def load_manifest() -> dict:
    manifest_path = Path(__file__).resolve().parents[1] / "manifest.json"
    if not manifest_path.exists():
        logger.warn(f"⚠️ manifest.json не найден: {manifest_path}")
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.err(f"[utils.load_manifest] Ошибка чтения manifest.json: {exc}")
        return {}


def get_elapsed_time(start_time: float) -> str:
    elapsed = time.time() - start_time
    if elapsed < 60:
        return f"{elapsed:.2f}s"
    minutes, seconds = divmod(int(elapsed), 60)
    return f"{minutes}m {seconds:02d}s"
