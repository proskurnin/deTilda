# -*- coding: utf-8 -*-
"""
main.py — основной контроллер пайплайна Detilda v4.5 LTS unified
Оркестрирует весь процесс: распаковка, очистка, переименование, внедрение, проверка и отчёт.
"""

import time
from pathlib import Path
from core import (
    logger,
    assets,
    cleaners,
    forms,
    inject,
    report,
    refs,
)
from core.utils import ensure_dir


def main():
    start_time = time.time()
    version = "v4.5 LTS unified"

    # === 1. Инициализация окружения ===
    workdir = Path("./_workdir")
    ensure_dir(workdir)
    print(f"=== Detilda {version} ===")
    print(f"Рабочая папка: {workdir.resolve()}")
    print(f"Дата запуска: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # === 2. Ввод параметров пользователя ===
    archive_name = input("Введите имя архива в папке ./_workdir (например, projectXXXX.zip): ").strip()
    email = input("Введите e-mail для отправки формы (по умолчанию r@prororo.com): ").strip() or "r@prororo.com"

    if not archive_name:
        print("❌ Имя архива не указано — завершение работы.")
        return

    archive_path = workdir / archive_name
    if not archive_path.exists():
        print(f"❌ Архив не найден: {archive_path}")
        return

    # === 3. Распаковка архива ===
    project_root = refs.unpack_archive(archive_path)
    if not project_root:
        print("💥 Ошибка распаковки архива. Завершение.")
        return

    # === 4. Привязка логгера ===
    logger.attach_to_project(project_root)
    logger.info(f"=== Detilda {version} ===")
    logger.info(f"Рабочая папка: {workdir.resolve()}")
    logger.info(f"Дата запуска: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"→ Используется адрес: {email}")

    # === 5. Переименование и очистка ассетов ===
    logger.info("🖼 Переименование и очистка ассетов...")
    stats = {}
    rename_map, stats = assets.rename_and_cleanup_assets(project_root, stats)

    renamed_count = stats.get("renamed", 0)
    removed_count = stats.get("removed", 0)
    logger.info(f"🖼 Ассеты обработаны: переименовано {renamed_count}, удалено {removed_count}")

    report.generate_intermediate_report(
        renamed=renamed_count,
        cleaned=0,
        fixed_links=0,
        broken_links=0
    )

    # === 6. Очистка файлов проекта ===
    logger.info("🧹 Очистка файлов проекта...")
    cleaned_count = cleaners.clean_project_files(project_root)
    logger.info(f"✅ Очистка завершена. Обновлено файлов: {cleaned_count}")

    report.generate_intermediate_report(
        renamed=renamed_count,
        cleaned=cleaned_count,
        fixed_links=0,
        broken_links=0
    )

    # === 7. Генерация send_email.php ===
    logger.info("📬 Генерация send_email.php...")
    try:
        forms.generate_send_email_php(project_root, email)
        logger.ok("📩 send_email.php успешно создан.")
    except Exception as e:
        logger.err(f"💥 Ошибка генерации send_email.php: {e}")

    # === 8. Внедрение form-handler.js ===
    logger.info("🧩 Внедрение form-handler.js и AIDA forms...")
    try:
        inject.inject_form_scripts(project_root)
        logger.ok("✅ Внедрение скриптов завершено.")
    except Exception as e:
        logger.err(f"💥 Ошибка при внедрении скриптов: {e}")

    # === 9. Обновление ссылок в проекте ===
    logger.info("🔗 Обновление ссылок в проекте...")
    try:
        fixed_links, broken_links = refs.update_all_refs_in_project(project_root, rename_map)
        logger.ok(f"✅ Исправлено ссылок: {fixed_links}, осталось битых: {broken_links}")
    except Exception as e:
        logger.err(f"💥 Ошибка при обновлении ссылок: {e}")
        fixed_links, broken_links = 0, 0

    report.generate_intermediate_report(
        renamed=renamed_count,
        cleaned=cleaned_count,
        fixed_links=fixed_links,
        broken_links=broken_links
    )

    # === 10. Финальная проверка ===
    warnings = 0  # пока не реализована отдельная проверка

    # === 11. Финальный отчёт ===
    exec_time = round(time.time() - start_time, 2)
    logger.info("📊 Формирование финального отчёта...")
    report.generate_final_report(
        project_root=project_root,
        renamed_count=renamed_count,
        warnings=warnings,
        broken_links_fixed=fixed_links,
        broken_links_left=broken_links,
        exec_time=exec_time,
    )

    # === 12. Завершение ===
    logger.info("======================================")
    logger.info(f"🎯  Detilda {version} — обработка завершена")
    logger.info(f"📦 Переименовано ассетов: {renamed_count}")
    logger.info(f"🧹 Очищено файлов: {cleaned_count}")
    logger.info(f"🔗 Исправлено ссылок: {fixed_links} / Осталось битых: {broken_links}")
    logger.info(f"⚠️ Предупреждений: {warnings}")
    logger.info(f"🕓 Время выполнения: {exec_time} сек")
    logger.info("======================================")
    logger.ok(f"🎯 Detilda {version} — завершено успешно.")
    logger.close()


if __name__ == "__main__":
    main()