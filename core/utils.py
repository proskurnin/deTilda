# -*- coding: utf-8 -*-
"""
utils.py — системные утилиты Detilda v4.4 LTS
Безопасное чтение, запись, создание каталогов и вспомогательные функции.
"""

import os
import io
import json
import time
from pathlib import Path
from core import logger


# === Безопасное чтение файла ===
def safe_read(path: str) -> str:
    """
    Безопасно читает текстовый файл и возвращает содержимое.
    Автоматически определяет кодировку (utf-8 / utf-8-sig).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")

    try:
        with io.open(path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with io.open(path, "r", encoding="utf-8-sig") as f:
            return f.read()
    except Exception as e:
        logger.err(f"[utils.safe_read] Ошибка при чтении {path}: {e}")
        return ""


# === Безопасная запись файла ===
def safe_write(path: str, content: str):
    """
    Безопасно записывает текст в файл с созданием всех промежуточных директорий.
    """
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with io.open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
    except Exception as e:
        logger.err(f"[utils.safe_write] Ошибка записи {path}: {e}")
        raise


# === Безопасное копирование ===
def safe_copy(src: str, dst: str):
    """
    Копирует файл с перезаписью и защитой от отсутствующих каталогов.
    """
    import shutil
    src = Path(src)
    dst = Path(dst)
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        logger.info(f"📄 Копия создана: {dst.name}")
    except Exception as e:
        logger.err(f"[utils.safe_copy] Ошибка копирования {src} → {dst}: {e}")


# === Очистка файла ===
def clear_file(path: str):
    """
    Очищает файл, оставляя его существующим (полезно для логов и временных файлов).
    """
    try:
        Path(path).write_text("", encoding="utf-8")
        logger.info(f"🧹 Очищен файл: {path}")
    except Exception as e:
        logger.err(f"[utils.clear_file] Ошибка очистки {path}: {e}")


# === Подсчёт строк в тексте ===
def count_lines(text: str) -> int:
    """Возвращает количество строк в тексте."""
    return text.count("\n") + 1 if text else 0


# === Проверка существования файла ===
def file_exists(path: str) -> bool:
    """Проверяет, существует ли файл."""
    return Path(path).exists()


# === Удаление файла ===
def safe_delete(path: str):
    """Безопасно удаляет файл, если он существует."""
    path = Path(path)
    try:
        if path.exists():
            path.unlink()
            logger.info(f"🗑 Удалён файл: {path}")
    except Exception as e:
        logger.err(f"[utils.safe_delete] Ошибка удаления {path}: {e}")


# === Получение относительного пути ===
def relpath(path: str, base: str) -> str:
    """
    Возвращает путь относительно base, с нормализованными разделителями.
    """
    try:
        return str(Path(path).resolve().relative_to(Path(base).resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


# === Безопасное создание папки ===
def ensure_dir(path: str):
    """Создаёт папку, если её нет."""
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.err(f"[utils.ensure_dir] Ошибка создания каталога {path}: {e}")


# === Чтение всех файлов в директории ===
def list_files_recursive(base_dir: str, extensions=None) -> list:
    """
    Возвращает список всех файлов в директории (рекурсивно).
    extensions — список разрешённых расширений (например: ['.html', '.js'])
    """
    base_dir = Path(base_dir)
    files = []
    for p in base_dir.rglob("*"):
        if p.is_file() and (not extensions or p.suffix.lower() in extensions):
            files.append(str(p))
    return files


# === Новый блок: чтение manifest.json ===
def load_manifest() -> dict:
    """
    Загружает manifest.json из корня проекта и возвращает его как dict.
    Если файл отсутствует — возвращает пустой словарь.
    """
    manifest_path = Path(__file__).resolve().parents[1] / "manifest.json"

    if not manifest_path.exists():
        logger.warn(f"⚠️ manifest.json не найден: {manifest_path}")
        return {}

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
            logger.info(f"📄 Manifest загружен: версия {manifest.get('version', 'unknown')}")
            return manifest
    except Exception as e:
        logger.err(f"[utils.load_manifest] Ошибка чтения manifest.json: {e}")
        return {}


# === Новый блок: форматирование времени выполнения ===
def get_elapsed_time(start_time: float) -> str:
    """
    Возвращает красиво отформатированное время выполнения скрипта:
    1.23s, 12.5s, 1m 03s, 2m 41s
    """
    elapsed = time.time() - start_time
    if elapsed < 60:
        return f"{elapsed:.2f}s"
    minutes, seconds = divmod(int(elapsed), 60)
    return f"{minutes}m {seconds:02d}s"


# === Прямая отладка ===
if __name__ == "__main__":
    test_file = "./_workdir/test_output.txt"
    try:
        safe_write(test_file, "Test OK ✅")
        text = safe_read(test_file)
        logger.info(f"Прочитано содержимое: {text.strip()}")
        clear_file(test_file)
        safe_delete(test_file)
    except Exception as e:
        logger.err(f"💥 Ошибка при тесте utils.py: {e}")