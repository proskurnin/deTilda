"""Pack a processed project folder into a ZIP archive (in memory).

Используется веб-сервисом после завершения pipeline:
  stats = process_archive(path, ...)
  zip_bytes = pack_result(stats.project_root)
  # → отдаём пользователю как файл для скачивания
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

__all__ = ["pack_result"]


def pack_result(project_root: Path) -> bytes:
    """Упаковывает обработанную папку в ZIP и возвращает байты.

    Структура внутри ZIP сохраняет относительные пути от project_root.
    Например: project_root/css/style.css → css/style.css в архиве.

    Бросает FileNotFoundError если project_root не существует.
    """
    project_root = Path(project_root)
    if not project_root.exists():
        raise FileNotFoundError(f"Папка проекта не найдена: {project_root}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(project_root.rglob("*")):
            if not file_path.is_file():
                continue
            arcname = file_path.relative_to(project_root)
            zf.write(file_path, arcname)

    return buf.getvalue()
