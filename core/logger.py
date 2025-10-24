# -*- coding: utf-8 -*-
"""
logger.py — централизованное логирование для Detilda v4.5 LTS unified
Создаёт logs/{project_name}_detilda.log и обеспечивает удобное форматирование вывода.
"""

import sys
import time
from pathlib import Path

# === Глобальное состояние ===
_log_file = None
_project_name = None
_logs_dir = None


# === Формат вывода ===
def _timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _write_line(level: str, message: str):
    """
    Записывает строку и в консоль, и в лог.
    """
    global _log_file
    line = f"{_timestamp()} {level} {message}"
    print(line)
    if _log_file:
        try:
            _log_file.write(line + "\n")
            _log_file.flush()
        except Exception:
            pass


# === Методы логирования ===
def info(msg: str): _write_line("ℹ️", msg)
def ok(msg: str): _write_line("✅", msg)
def warn(msg: str): _write_line("⚠️", msg)
def err(msg: str): _write_line("💥", msg)
def debug(msg: str): _write_line("🐞", msg)


# === Инициализация логов ===
def attach_to_project(project_root: Path):
    """
    Привязывает логирование к проекту.
    Создаёт logs/{project_name}_detilda.log рядом со скриптом.
    """
    global _log_file, _project_name, _logs_dir

    _project_name = project_root.name
    base_dir = project_root.parent.parent if project_root.parent.name == "_workdir" else project_root.parent
    _logs_dir = base_dir / "logs"
    _logs_dir.mkdir(parents=True, exist_ok=True)

    log_path = _logs_dir / f"{_project_name}_detilda.log"

    try:
        _log_file = open(log_path, "a", encoding="utf-8")
        header = (
            f"\n{'=' * 80}\n"
            f"🕓 {_timestamp()} — Detilda log started for '{_project_name}'\n"
            f"{'=' * 80}\n"
        )
        _log_file.write(header)
        _log_file.flush()
        print(header, end="")
        _write_line("ℹ️", f"Лог-файл: {log_path}")
    except Exception as e:
        print(f"💥 Ошибка открытия лога: {e}", file=sys.stderr)
        _log_file = None


def get_project_name() -> str:
    """Возвращает имя текущего проекта."""
    return _project_name or "detilda"


def get_logs_dir() -> Path:
    """Возвращает путь к каталогу логов."""
    return _logs_dir or Path("logs")


def close():
    """
    Завершает логирование.
    """
    global _log_file
    if _log_file:
        try:
            footer = (
                f"{'=' * 80}\n"
                f"🏁 Завершение Detilda для {_project_name or 'неизвестного проекта'}\n"
                f"{'=' * 80}\n\n"
            )
            _log_file.write(footer)
            _log_file.close()
        except Exception:
            pass
        _log_file = None