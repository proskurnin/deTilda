"""Archive extraction helpers."""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from core import logger

__all__ = ["unpack_archive"]


def unpack_archive(archive_path: Path) -> Path | None:
    """Extract *archive_path* into the parent directory and return project root."""

    archive_path = Path(archive_path)
    if not archive_path.exists():
        logger.err(f"Архив не найден: {archive_path}")
        return None

    workdir = archive_path.parent
    logger.info("📦 Распаковка архива...")

    try:
        with zipfile.ZipFile(archive_path, "r") as handle:
            entries = handle.namelist()
            roots = {Path(name).parts[0] for name in entries if name}
            target_root: Path
            if len(roots) == 1:
                (root_name,) = roots
                target_root = workdir / root_name
                logger.info(
                    f"Обнаружена единственная корневая папка: '{root_name}'. Распаковка с сохранением структуры..."
                )
                if target_root.exists():
                    shutil.rmtree(target_root)
                handle.extractall(workdir)
            else:
                target_root = workdir / archive_path.stem
                if target_root.exists():
                    shutil.rmtree(target_root)
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
