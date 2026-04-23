"""Simple logging utilities used across the Detilda toolchain."""
from __future__ import annotations

import sys
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional, TextIO

__all__ = [
    "attach_to_project",
    "close",
    "debug",
    "error",
    "err",
    "exception",
    "get_logs_dir",
    "get_project_name",
    "info",
    "module_scope",
    "ok",
    "warn",
]

_log_file: Optional[TextIO] = None
_project_name: str = "detilda"
_logs_dir: Optional[Path] = None


def _timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _write_line(level: str, message: str) -> None:
    global _log_file
    line = f"{_timestamp()} {level} {message}"
    print(line)
    if _log_file is not None:
        try:
            _log_file.write(line + "\n")
            _log_file.flush()
        except Exception:
            # Logging errors must never crash the pipeline.
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
    """Log *message* with the active traceback."""

    _write_line("💥", message)
    tb = traceback.format_exc().rstrip()
    if tb and tb != "NoneType: None":
        for line in tb.splitlines():
            _write_line("💥", line)


@contextmanager
def module_scope(module_name: str) -> Iterator[None]:
    """Log start and finish messages for a logical application module."""

    start = time.time()
    info(f"[{module_name}] ▶️ Начало работы")
    try:
        yield
    finally:
        duration = time.time() - start
        info(f"[{module_name}] ✅ Завершено за {duration:.2f} сек")


def attach_to_project(project_root: Path, logs_dir: Optional[Path] = None) -> None:
    """Initialise logging for *project_root*.

    logs_dir: путь к папке логов; если не передан — вычисляется относительно project_root.
    """

    global _log_file, _project_name, _logs_dir

    project_root = Path(project_root)
    _project_name = project_root.name

    if logs_dir is not None:
        _logs_dir = Path(logs_dir)
    else:
        base_dir = (
            project_root.parent.parent
            if project_root.parent.name == "_workdir"
            else project_root.parent
        )
        _logs_dir = base_dir / "logs"

    _logs_dir.mkdir(parents=True, exist_ok=True)

    log_path = _logs_dir / f"{_project_name}_detilda.log"

    try:
        _log_file = log_path.open("a", encoding="utf-8")
    except Exception as exc:  # pragma: no cover - defensive fallback
        print(f"💥 Не удалось открыть файл лога {log_path}: {exc}", file=sys.stderr)
        _log_file = None
        return

    header = (
        f"{'=' * 80}\n"
        f"🕓 {_timestamp()} — deTilda log started for '{_project_name}'\n"
        f"{'=' * 80}\n"
    )
    _log_file.write(header)
    _log_file.flush()
    print(header, end="")
    info(f"Лог-файл: {log_path}")


def get_project_name() -> str:
    return _project_name


def get_logs_dir() -> Path:
    return _logs_dir or Path("logs")


def close() -> None:
    global _log_file
    if _log_file is None:
        return
    footer = (
        f"{'=' * 80}\n"
        f"🏁 Завершение deTilda для {_project_name}\n"
        f"{'=' * 80}\n\n"
    )
    try:
        _log_file.write(footer)
        _log_file.close()
    except Exception:
        pass
    finally:
        _log_file = None
