"""Simple logging utilities used across the deTilda toolchain.

Жизненный цикл:
  1. attach_to_project() — открывает лог-файл для текущего проекта
  2. info/warn/err/ok/debug — пишут в консоль И в файл одновременно
  3. close() — закрывает файл (вызывается в finally блоке pipeline)

Имя лог-файла: logs/<project>_detilda.log

Состояние хранится в contextvars.ContextVar — каждый asyncio-таск (веб-запрос)
получает изолированный лог-файл без дополнительной настройки.
"""
from __future__ import annotations

import sys
import time
import traceback
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator, Optional, TextIO

__all__ = [
    "attach_to_project",
    "close",
    "debug",
    "err",
    "exception",
    "get_logs_dir",
    "get_project_name",
    "info",
    "module_scope",
    "ok",
    "warn",
]

# Суффикс в имени лог-файла: <project>_detilda.log
_LOG_SUFFIX = "detilda"

# Состояние логгера в ContextVar — изолировано на уровне asyncio-таска/потока.
# Каждый веб-запрос (asyncio.create_task) получает свою копию автоматически.
_log_file_var: ContextVar[Optional[TextIO]] = ContextVar("_log_file", default=None)
_project_name_var: ContextVar[str] = ContextVar("_project_name", default="")
_logs_dir_var: ContextVar[Optional[Path]] = ContextVar("_logs_dir", default=None)


def _timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _write_line(level: str, message: str) -> None:
    """Пишет строку одновременно в консоль и в лог-файл."""
    line = f"{_timestamp()} {level} {message}"
    print(line)
    log_file = _log_file_var.get()
    if log_file is not None:
        try:
            log_file.write(line + "\n")
            log_file.flush()
        except Exception:
            # Ошибки логгера не должны останавливать pipeline.
            pass


def info(message: str) -> None:
    _write_line("ℹ️", message)


def ok(message: str) -> None:
    _write_line("✅", message)


def warn(message: str) -> None:
    _write_line("⚠️", message)


def err(message: str) -> None:
    _write_line("💥", message)


def error(message: str) -> None:
    """Backward-compatible alias for :func:`err`."""
    err(message)


def debug(message: str) -> None:
    _write_line("🐞", message)


def exception(message: str) -> None:
    """Логирует сообщение вместе с активным traceback."""
    _write_line("💥", message)
    tb = traceback.format_exc().rstrip()
    if tb and tb != "NoneType: None":
        for line in tb.splitlines():
            _write_line("💥", line)


@contextmanager
def module_scope(module_name: str) -> Iterator[None]:
    """Контекстный менеджер: логирует начало и конец шага конвейера с временем выполнения."""
    start = time.time()
    info(f"[{module_name}] ▶️ Начало работы")
    try:
        yield
    finally:
        duration = time.time() - start
        info(f"[{module_name}] ✅ Завершено за {duration:.2f} сек")


def attach_to_project(project_root: Path, logs_dir: Optional[Path] = None) -> None:
    """Инициализирует логирование для конкретного проекта.

    Вызывается в начале обработки каждого архива.
    logs_dir: путь из manifest.json; если не передан — вычисляется автоматически.
    Состояние изолировано через ContextVar — безопасно при конкурентных вызовах.
    """
    project_root = Path(project_root)
    # Имя проекта = имя папки архива (например "hotelsargis")
    project_name = project_root.name
    _project_name_var.set(project_name)

    if logs_dir is not None:
        resolved_logs_dir = Path(logs_dir)
    else:
        # Если проект в _workdir/ — поднимаемся на два уровня до корня репо
        base_dir = (
            project_root.parent.parent
            if project_root.parent.name == "_workdir"
            else project_root.parent
        )
        resolved_logs_dir = base_dir / "logs"

    resolved_logs_dir.mkdir(parents=True, exist_ok=True)
    _logs_dir_var.set(resolved_logs_dir)

    log_path = resolved_logs_dir / f"{project_name}_{_LOG_SUFFIX}.log"

    try:
        # Открываем в режиме append — повторный прогон дописывает в тот же файл
        log_file = log_path.open("a", encoding="utf-8")
        _log_file_var.set(log_file)
    except Exception as exc:  # pragma: no cover - defensive fallback
        print(f"💥 Не удалось открыть файл лога {log_path}: {exc}", file=sys.stderr)
        _log_file_var.set(None)
        return

    header = (
        f"{'=' * 80}\n"
        f"🕓 {_timestamp()} — deTilda log started for '{project_name}'\n"
        f"{'=' * 80}\n"
    )
    log_file.write(header)
    log_file.flush()
    print(header, end="")
    info(f"Лог-файл: {log_path}")


def get_project_name() -> str:
    """Возвращает имя текущего проекта (используется в report.py для имени файла отчёта)."""
    return _project_name_var.get()


def get_logs_dir() -> Path:
    """Возвращает папку логов (используется в assets.py для сохранения rename_map)."""
    return _logs_dir_var.get() or Path("logs")


def close() -> None:
    """Закрывает лог-файл. Вызывается в finally блоке pipeline после обработки архива."""
    log_file = _log_file_var.get()
    if log_file is None:
        return
    footer = (
        f"{'=' * 80}\n"
        f"🏁 Завершение deTilda для {_project_name_var.get()}\n"
        f"{'=' * 80}\n\n"
    )
    try:
        log_file.write(footer)
        log_file.close()
    except Exception:
        pass
    finally:
        _log_file_var.set(None)
