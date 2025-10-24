"""Simple logging utilities used across the Detilda toolchain."""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional, TextIO

__all__ = [
    "attach_to_project",
    "close",
    "debug",
    "err",
    "get_logs_dir",
    "get_project_name",
    "info",
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


def debug(message: str) -> None:
    _write_line("🐞", message)


def attach_to_project(project_root: Path) -> None:
    """Initialise logging for *project_root*."""

    global _log_file, _project_name, _logs_dir

    project_root = Path(project_root)
    _project_name = project_root.name
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
        f"🕓 {_timestamp()} — Detilda log started for '{_project_name}'\n"
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
        f"🏁 Завершение Detilda для {_project_name}\n"
        f"{'=' * 80}\n\n"
    )
    try:
        _log_file.write(footer)
        _log_file.close()
    except Exception:
        pass
    finally:
        _log_file = None
