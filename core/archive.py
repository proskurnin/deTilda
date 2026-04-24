"""Archive extraction helpers for the deTilda pipeline.

Поддерживает два режима распаковки ZIP-архива:

  1. Единственная корневая папка внутри архива (стандартный экспорт Tilda):
       project12345.zip
         └── project12345/
               ├── index.html
               └── ...
     → распаковывается напрямую в _workdir/project12345/

  2. Несколько объектов в корне архива (нестандартная структура):
       archive.zip
         ├── index.html
         ├── css/
         └── ...
     → распаковывается во временную папку, затем перемещается в _workdir/<имя_архива>/

Если папка назначения уже существует — удаляется перед распаковкой
(предыдущий результат обработки заменяется новым).
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from core import logger

__all__ = ["unpack_archive"]


def unpack_archive(archive_path: Path) -> Path | None:
    """Распаковывает архив в родительскую папку и возвращает путь к корню проекта.

    Возвращает None при любой ошибке — pipeline останавливает обработку этого архива.
    """
    archive_path = Path(archive_path)
    if not archive_path.exists():
        logger.err(f"Архив не найден: {archive_path}")
        return None

    workdir = archive_path.parent
    logger.info("📦 Распаковка архива...")

    try:
        with zipfile.ZipFile(archive_path, "r") as handle:
            entries = handle.namelist()

            # Определяем уникальные корневые элементы архива
            roots = {Path(name).parts[0] for name in entries if name}

            if len(roots) == 1:
                # Режим 1: стандартный экспорт Tilda — одна корневая папка
                (root_name,) = roots
                target_root = workdir / root_name
                logger.info(
                    f"Обнаружена единственная корневая папка: '{root_name}'. "
                    "Распаковка с сохранением структуры..."
                )
                if target_root.exists():
                    logger.info(f"[archive] Удаляем существующую папку: {target_root.name}")
                    shutil.rmtree(target_root)
                handle.extractall(workdir)
            else:
                # Режим 2: файлы в корне архива — оборачиваем в папку по имени архива
                target_root = workdir / archive_path.stem
                if target_root.exists():
                    logger.info(f"[archive] Удаляем существующую папку: {target_root.name}")
                    shutil.rmtree(target_root)

                # Распаковываем во временную папку, затем переносим
                tmp_dir = workdir / "_detilda_extract_tmp"
                if tmp_dir.exists():
                    shutil.rmtree(tmp_dir)
                handle.extractall(tmp_dir)
                target_root.mkdir(parents=True, exist_ok=True)
                for item in tmp_dir.iterdir():
                    shutil.move(str(item), target_root / item.name)
                shutil.rmtree(tmp_dir, ignore_errors=True)

    except zipfile.BadZipFile as exc:
        logger.err(f"💥 Некорректный ZIP-архив: {exc}")
        return None
    except Exception as exc:  # pragma: no cover - defensive branch
        logger.err(f"💥 Ошибка распаковки архива: {exc}")
        return None

    logger.info(f"→ Распаковка завершена: {target_root}")
    return target_root
