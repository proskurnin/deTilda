# -*- coding: utf-8 -*-
"""CLI entry point orchestrating the Detilda pipeline."""
from __future__ import annotations

from time import time as _now
from pathlib import Path

from core import (
    archive,
    assets,
    checker,
    cleaners,
    forms,
    inject,
    logger,
    page404,
    refs,
    report,
    script_cleaner,
)
from core.config_loader import ConfigLoader
from core.utils import ensure_dir, get_elapsed_time, load_manifest

VERSION = "v4.5.0 LTS unified"


def _prompt(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""


def _process_archive(
    archive_name: str,
    workdir: Path,
    email: str,
    version: str,
) -> None:
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
        with logger.module_scope("assets"):
            asset_result = assets.rename_and_cleanup_assets(project_root, loader)

        with logger.module_scope("page404"):
            page404.update_404_page(project_root)

        report.generate_intermediate_report(
            renamed=asset_result.stats.renamed,
            cleaned=0,
            fixed_links=0,
            broken_links=0,
        )

        with logger.module_scope("cleaners"):
            clean_stats = cleaners.clean_text_files(project_root, loader)

        report.generate_intermediate_report(
            renamed=asset_result.stats.renamed,
            cleaned=clean_stats.updated,
            fixed_links=0,
            broken_links=0,
        )

        with logger.module_scope("forms"):
            forms.generate_send_email_php(project_root, email)

        with logger.module_scope("inject"):
            inject.inject_form_scripts(project_root, loader)

        with logger.module_scope("refs"):
            fixed_links, broken_links = refs.update_all_refs_in_project(
                project_root, asset_result.rename_map, loader
            )

        with logger.module_scope("script_cleaner"):
            script_cleaner.remove_disallowed_scripts(project_root, loader)

        with logger.module_scope("checker"):
            link_check = checker.check_links(project_root, loader)

        exec_time = _now() - start
        with logger.module_scope("report"):
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


def main() -> None:
    manifest = load_manifest()
    version = manifest.get("version", VERSION)
    workdir = ensure_dir(Path(manifest.get("paths", {}).get("workdir", "_workdir")))

    print(f"=== Detilda {version} ===")
    print(f"Рабочая папка: {workdir.resolve()}")

    archive_prompt = (
        "Введите имя архива в ./_workdir (например, projectXXXX.zip). "
        "Можно перечислить несколько через запятую: "
    )
    archive_input = _prompt(archive_prompt).strip()
    if not archive_input:
        print("❌ Имя архива не указано — завершение работы.")
        return

    archive_names = [name.strip() for name in archive_input.split(",") if name.strip()]
    if not archive_names:
        print("❌ Имя архива не указано — завершение работы.")
        return

    email = _prompt("Введите e-mail для отправки формы (по умолчанию r@prororo.com): ").strip() or "r@prororo.com"

    for index, archive_name in enumerate(archive_names, start=1):
        if len(archive_names) > 1:
            print("======================================")
            print(f"▶️  {index}/{len(archive_names)}: обработка архива {archive_name}")

        _process_archive(archive_name, workdir, email, version)


if __name__ == "__main__":
    main()
