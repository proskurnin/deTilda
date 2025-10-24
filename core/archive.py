# -*- coding: utf-8 -*-
"""
archive.py — модуль распаковки архива Detilda v4.2 LTS
Отвечает за корректную распаковку .zip в _workdir и определение корневой папки проекта.
"""

import os
import zipfile
import shutil
from core import logger


def unzip_archive(archive_path: str, workdir: str) -> str:
    """
    Распаковывает архив .zip в рабочую директорию и возвращает путь к корневой папке проекта.
    Если внутри архива единственная папка — извлекает её структуру как есть.
    """
    if not os.path.exists(archive_path):
        raise FileNotFoundError(f"Архив не найден: {archive_path}")

    extract_dir = os.path.join(workdir, "_unzipped_tmp")
    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)
    os.makedirs(extract_dir, exist_ok=True)

    logger.info(f"→ Распаковка архива: {os.path.basename(archive_path)}")

    try:
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)
    except zipfile.BadZipFile:
        raise RuntimeError(f"Некорректный ZIP-архив: {archive_path}")

    # Найдём корневой элемент (обычно это одна папка)
    root_items = os.listdir(extract_dir)
    if not root_items:
        raise RuntimeError("Архив пуст — нечего распаковывать.")

    # Если внутри архива одна папка — используем её как корень
    if len(root_items) == 1:
        root_folder = os.path.join(extract_dir, root_items[0])
        if os.path.isdir(root_folder):
            project_root = os.path.join(workdir, root_items[0])

            logger.info(
                f"Обнаружена единственная корневая папка в архиве: '{os.path.basename(root_folder)}'. "
                "Распаковка с сохранением структуры..."
            )

            # Если в рабочей папке уже есть проект с тем же именем — удаляем
            if os.path.exists(project_root):
                shutil.rmtree(project_root)

            shutil.move(root_folder, project_root)
            shutil.rmtree(extract_dir, ignore_errors=True)
            return project_root

    # Если структура сложная (файлы/папки вперемешку)
    logger.info("Несколько элементов в корне архива. Распаковка напрямую в _workdir...")
    project_root = os.path.join(workdir, "project_manual_import")
    if os.path.exists(project_root):
        shutil.rmtree(project_root)

    os.makedirs(project_root, exist_ok=True)
    for item in root_items:
        src = os.path.join(extract_dir, item)
        dst = os.path.join(project_root, item)
        shutil.move(src, dst)

    shutil.rmtree(extract_dir, ignore_errors=True)
    return project_root


# === Прямая отладка ===
if __name__ == "__main__":
    test_archive = "./_workdir/project5059034.zip"
    test_workdir = "./_workdir"
    try:
        result = unzip_archive(test_archive, test_workdir)
        logger.info(f"✅ Проект распакован в: {result}")
    except Exception as e:
        logger.err(f"💥 Ошибка при распаковке: {e}")