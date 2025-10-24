# -*- coding: utf-8 -*-
"""CLI entry point orchestrating the Detilda pipeline."""
from __future__ import annotations

from time import time as _now
from pathlib import Path

from core import archive, assets, checker, cleaners, forms, inject, logger, refs, report
from core.config_loader import ConfigLoader
from core.utils import ensure_dir, get_elapsed_time, load_manifest

VERSION = "v4.5.0 LTS unified"


def _prompt(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""


def main() -> None:
    manifest = load_manifest()
    version = manifest.get("version", VERSION)
    workdir = ensure_dir(Path(manifest.get("paths", {}).get("workdir", "_workdir")))

    print(f"=== Detilda {version} ===")
    print(f"Рабочая папка: {workdir.resolve()}")

    archive_name = _prompt("Введите имя архива в ./_workdir (например, projectXXXX.zip): ").strip()
    if not archive_name:
        print("❌ Имя архива не указано — завершение работы.")
        return

    email = _prompt("Введите e-mail для отправки формы (по умолчанию r@prororo.com): ").strip() or "r@prororo.com"

    archive_path = workdir / archive_name
    if not archive_path.exists():
        print(f"❌ Архив не найден: {archive_path}")
        return

    project_root = archive.unpack_archive(archive_path)
    if project_root is None:
        print("💥 Не удалось распаковать архив.")
        return

    logger.attach_to_project(project_root)
    loader = ConfigLoader(Path(__file__).resolve().parent)

    start = _now()
    try:
        asset_result = assets.rename_and_cleanup_assets(project_root, loader)
        report.generate_intermediate_report(
            renamed=asset_result.stats.renamed,
            cleaned=0,
            fixed_links=0,
            broken_links=0,
        )

        clean_stats = cleaners.clean_text_files(project_root, loader)
        report.generate_intermediate_report(
            renamed=asset_result.stats.renamed,
            cleaned=clean_stats.updated,
            fixed_links=0,
            broken_links=0,
        )

        forms.generate_send_email_php(project_root, email)
        inject.inject_form_scripts(project_root, loader)

        fixed_links, broken_links = refs.update_all_refs_in_project(
            project_root, asset_result.rename_map, loader
        )

        link_check = checker.check_links(project_root, loader)

        exec_time = _now() - start
        report.generate_final_report(
            project_root=project_root,
            renamed_count=asset_result.stats.renamed,
            warnings=link_check.broken,
            broken_links_fixed=fixed_links,
            broken_links_left=broken_links + link_check.broken,
            exec_time=exec_time,
        )

        logger.info("======================================")
        logger.info(f"🎯  Detilda {version} — обработка завершена")
        logger.info(f"📦 Переименовано ассетов: {asset_result.stats.renamed}")
        logger.info(f"🧹 Очищено файлов: {clean_stats.updated}")
        logger.info(
            f"🔗 Исправлено ссылок: {fixed_links} / Осталось битых: {broken_links + link_check.broken}"
        )
        logger.info(f"⚠️ Предупреждений: {link_check.broken}")
        logger.info(f"🕓 Время выполнения: {get_elapsed_time(start)}")
        logger.info("======================================")
        logger.ok(f"🎯 Detilda {version} — завершено успешно.")
    finally:
        logger.close()


if __name__ == "__main__":
    main()
