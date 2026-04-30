"""Reusable helper utilities for the deTilda toolkit.

Набор низкоуровневых функций без бизнес-логики.
Используются во всех модулях конвейера.
Не импортируют ничего из других модулей core/, кроме logger.
"""
from __future__ import annotations

import json
import shutil
import time
from contextvars import ContextVar
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

# Устанавливается в DetildaPipeline.run() когда dry_run=True.
# safe_write/safe_copy/safe_delete становятся no-op — файлы не изменяются.
_dry_run: ContextVar[bool] = ContextVar("_dry_run", default=False)


def _to_path(path: Path | str) -> Path:
    return path if isinstance(path, Path) else Path(path)


def safe_read(path: Path | str) -> str:
    """Читает файл как UTF-8 строку. Обрабатывает BOM (utf-8-sig) как запасной вариант."""
    path_obj = _to_path(path)
    if not path_obj.exists():
        raise FileNotFoundError(f"Файл не найден: {path_obj}")
    try:
        return path_obj.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Некоторые Windows-редакторы сохраняют файлы с BOM-маркером
        return path_obj.read_text(encoding="utf-8-sig")


def safe_write(path: Path | str, content: str) -> None:
    """Записывает строку в файл UTF-8 с Unix-переносами. Создаёт папки если нужно."""
    if _dry_run.get():
        return
    path_obj = _to_path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    path_obj.write_text(content, encoding="utf-8", newline="\n")


def safe_copy(src: Path | str, dst: Path | str) -> None:
    """Копирует файл, создавая целевую папку если нужно."""
    if _dry_run.get():
        return
    src_path = _to_path(src)
    dst_path = _to_path(dst)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, dst_path)
    logger.info(f"📄 Копия создана: {dst_path.name}")


def safe_delete(path: Path | str) -> None:
    """Удаляет файл если он существует. Не падает если файла нет."""
    if _dry_run.get():
        return
    path_obj = _to_path(path)
    if path_obj.exists():
        path_obj.unlink()
        logger.info(f"🗑 Удалён файл: {path_obj}")


def relpath(path: Path | str, base: Path | str) -> str:
    """Возвращает путь к файлу относительно base. При ошибке — только имя файла."""
    path_obj = _to_path(path).resolve()
    base_obj = _to_path(base).resolve()
    try:
        return str(path_obj.relative_to(base_obj)).replace("\\", "/")
    except ValueError:
        return path_obj.name


def ensure_dir(path: Path | str) -> Path:
    """Создаёт папку если не существует. Возвращает Path для удобства цепочек."""
    path_obj = _to_path(path)
    path_obj.mkdir(parents=True, exist_ok=True)
    return path_obj


def list_files_recursive(base_dir: Path | str, extensions: Sequence[str] | None = None) -> list[Path]:
    """Рекурсивно обходит папку и возвращает файлы с нужными расширениями.

    extensions: например [".html", ".css"] — регистр не важен.
    Если extensions не задан — возвращает все файлы.
    """
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
    """Загружает manifest.json из корня проекта.

    Используется в main.py для чтения версии, путей и настроек.
    При ошибке возвращает пустой dict — приложение продолжает работу с дефолтами.
    """
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
    """Форматирует прошедшее время в читаемую строку: '12.34s' или '2m 05s'."""
    elapsed = time.time() - start_time
    if elapsed < 60:
        return f"{elapsed:.2f}s"
    minutes, seconds = divmod(int(elapsed), 60)
    return f"{minutes}m {seconds:02d}s"
