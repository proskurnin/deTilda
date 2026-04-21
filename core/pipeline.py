"""High level orchestration for the Detilda toolchain."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from core import assets, cleaners, forms, fonts_localizer, inject, logger, refs, report, script_cleaner
from core.project import ProjectContext


@dataclass
class PipelineStats:
    renamed: int = 0
    removed: int = 0
    cleaned: int = 0
    fixed_links: int = 0
    broken_links: int = 0
    warnings: int = 0
    exec_time: float = 0.0


class DetildaPipeline:
    def __init__(self, version: str = "v5.0 refactored") -> None:
        self.version = version

    def run(self, archive_path: Path, email: str) -> PipelineStats:
        start_time = time.time()

        project_root = refs.unpack_archive(archive_path)
        if not project_root:
            raise RuntimeError("Не удалось распаковать архив")

        context = ProjectContext.from_project_root(project_root)
        context.attach_logger()

        try:
            logger.info(f"=== Detilda {self.version} ===")
            logger.info(f"Рабочая папка: {archive_path.parent.resolve()}")
            logger.info(f"Дата запуска: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"→ Используется адрес: {email}")

            stats = PipelineStats()

            with logger.module_scope("assets"):
                asset_result = assets.rename_and_cleanup_assets(context)
            stats.renamed = asset_result.stats.renamed
            stats.removed = asset_result.stats.removed
            report.generate_intermediate_report(stats.renamed, 0, 0, 0)

            with logger.module_scope("cleaners"):
                clean_result = cleaners.clean_project_files(context, context.rename_map)
            stats.cleaned = clean_result.updated
            stats.removed += clean_result.removed
            report.generate_intermediate_report(stats.renamed, stats.cleaned, 0, 0)

            with logger.module_scope("forms"):
                forms.generate_send_email_php(context, email)
            with logger.module_scope("inject"):
                inject.inject_form_scripts(context)

            with logger.module_scope("fonts"):
                fonts_localizer.localize_google_fonts(context.project_root)

            with logger.module_scope("refs"):
                fixed_links, broken_links = refs.update_all_refs_in_project(
                    context.project_root, context.rename_map
                )
            stats.fixed_links = fixed_links
            stats.broken_links = broken_links
            report.generate_intermediate_report(
                stats.renamed, stats.cleaned, stats.fixed_links, stats.broken_links
            )

            with logger.module_scope("script_cleaner"):
                script_cleaner.remove_disallowed_scripts(
                    context.project_root, context.config_loader
                )

            stats.exec_time = time.time() - start_time
            with logger.module_scope("report"):
                report.generate_final_report(
                    project_root=context.project_root,
                    renamed_count=stats.renamed,
                    warnings=stats.warnings,
                    broken_links_fixed=stats.fixed_links,
                    broken_links_left=stats.broken_links,
                    exec_time=stats.exec_time,
                )

            logger.info("======================================")
            logger.info(f"🎯  Detilda {self.version} — обработка завершена")
            logger.info(f"📦 Переименовано ассетов: {stats.renamed}")
            logger.info(f"🧹 Очищено файлов: {stats.cleaned}")
            logger.info(
                f"🔗 Исправлено ссылок: {stats.fixed_links} / Осталось битых: {stats.broken_links}"
            )
            logger.info(f"⚠️ Предупреждений: {stats.warnings}")
            logger.info(f"🕓 Время выполнения: {stats.exec_time:.2f} сек")
            logger.info("======================================")
            logger.ok(f"🎯 Detilda {self.version} — завершено успешно.")

            return stats
        finally:
            logger.close()
