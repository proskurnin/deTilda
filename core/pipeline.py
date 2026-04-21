"""High level orchestration for the Detilda toolchain."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
import re

from core import (
    assets,
    checker,
    cleaners,
    forms,
    fonts_localizer,
    inject,
    logger,
    refs,
    report,
    script_cleaner,
)
from core.project import ProjectContext
from core.htaccess import get_missing_routes


@dataclass
class PipelineStats:
    renamed_assets: int = 0
    removed_assets: int = 0
    cleaned_files: int = 0
    fixed_links: int = 0
    broken_links: int = 0
    broken_htaccess_routes: int = 0
    ssl_bypassed_downloads: int = 0
    warnings: int = 0
    errors: int = 0
    downloaded_remote_assets: int = 0
    forms_found: int = 0
    forms_hooked: int = 0
    exec_time: float = 0.0

    @property
    def renamed(self) -> int:
        return self.renamed_assets

    @renamed.setter
    def renamed(self, value: int) -> None:
        self.renamed_assets = value

    @property
    def removed(self) -> int:
        return self.removed_assets

    @removed.setter
    def removed(self, value: int) -> None:
        self.removed_assets = value

    @property
    def cleaned(self) -> int:
        return self.cleaned_files

    @cleaned.setter
    def cleaned(self, value: int) -> None:
        self.cleaned_files = value


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
            stats.renamed_assets = asset_result.stats.renamed
            stats.removed_assets = asset_result.stats.removed
            stats.downloaded_remote_assets = asset_result.stats.downloaded
            stats.ssl_bypassed_downloads = asset_result.stats.ssl_bypassed_downloads
            stats.warnings += asset_result.stats.warnings
            report.generate_intermediate_report(stats.renamed_assets, 0, 0, 0)

            with logger.module_scope("cleaners"):
                clean_result = cleaners.clean_project_files(context, context.rename_map)
            stats.cleaned_files = clean_result.updated
            stats.removed_assets += clean_result.removed
            report.generate_intermediate_report(stats.renamed_assets, stats.cleaned_files, 0, 0)

            with logger.module_scope("forms"):
                forms.generate_send_email_php(context, email)
            stats.forms_found = self._count_forms(context.project_root)
            with logger.module_scope("inject"):
                stats.forms_hooked = inject.inject_form_scripts(context)

            with logger.module_scope("fonts"):
                fonts_localizer.localize_google_fonts(context.project_root)

            with logger.module_scope("refs"):
                fixed_links, broken_links = refs.update_all_refs_in_project(
                    context.project_root, context.rename_map, stats=stats
                )
            stats.fixed_links = fixed_links
            stats.broken_links = broken_links
            report.generate_intermediate_report(
                stats.renamed_assets, stats.cleaned_files, stats.fixed_links, stats.broken_links
            )

            with logger.module_scope("script_cleaner"):
                if script_cleaner.can_remove_tilda_form_scripts(context.project_root):
                    logger.info(
                        "[script_cleaner] Пользовательский обработчик форм найден, "
                        "удаляем Tilda form/events/fallback"
                    )
                    script_cleaner.remove_disallowed_scripts(
                        context.project_root, context.config_loader
                    )
                else:
                    logger.error(
                        "[script_cleaner] send_email.php или js/form-handler.js отсутствуют — "
                        "удаление Tilda-скриптов отменено"
                    )
                    stats.errors += 1

            with logger.module_scope("forms_check"):
                forms_check = checker.check_forms_integration(context.project_root)
            stats.forms_found = forms_check.forms_found
            stats.forms_hooked = forms_check.forms_hooked
            stats.warnings += forms_check.warnings

            stats.exec_time = time.time() - start_time
            with logger.module_scope("report"):
                report.generate_final_report(
                    project_root=context.project_root,
                    renamed_count=stats.renamed_assets,
                    warnings=stats.warnings,
                    broken_links_fixed=stats.fixed_links,
                    broken_links_left=stats.broken_links,
                    broken_htaccess_routes=stats.broken_htaccess_routes,
                    missing_htaccess_routes=[
                        (item.alias, item.target, item.action, item.replacement)
                        for item in get_missing_routes()
                    ],
                    exec_time=stats.exec_time,
                )


            self._print_final_summary(stats, stats.exec_time)

            return stats
        finally:
            logger.close()


    def _print_final_summary(self, stats: PipelineStats, elapsed_seconds: float) -> None:
        derived_warnings = stats.broken_links + stats.broken_htaccess_routes
        stats.warnings = max(stats.warnings, derived_warnings)

        logger.info("======================================")
        logger.info(f"🎯  Detilda {self.version} — обработка завершена")
        logger.info(f"📦 Переименовано ассетов: {stats.renamed_assets}")
        logger.info(f"🗑 Удалено ассетов: {stats.removed_assets}")
        logger.info(f"🧹 Очищено файлов: {stats.cleaned_files}")
        logger.info(f"🌐 Загружено удалённых ассетов: {stats.downloaded_remote_assets}")
        logger.info(f"🔐 SSL bypass downloads: {stats.ssl_bypassed_downloads}")
        logger.info(f"🔗 Исправлено ссылок: {stats.fixed_links}")
        logger.info(f"❌ Битых внутренних ссылок: {stats.broken_links}")
        logger.info(f"❌ Битых htaccess-маршрутов: {stats.broken_htaccess_routes}")
        logger.info(f"📝 Форм найдено: {stats.forms_found}")
        logger.info(f"🧩 Форм подключено к handler: {stats.forms_hooked}")
        logger.info(f"⚠️ Предупреждений: {stats.warnings}")
        logger.info(f"⛔ Ошибок: {stats.errors}")
        logger.info(f"🕓 Время выполнения: {elapsed_seconds:.2f} сек")

        logger.info("⚠️ Предупреждения (детализация):")
        if stats.broken_links > 0:
            logger.warn(f"  • Найдены битые внутренние ссылки: {stats.broken_links}")
        if stats.broken_htaccess_routes > 0:
            logger.warn(f"  • Найдены битые htaccess-маршруты: {stats.broken_htaccess_routes}")
        if stats.warnings == 0:
            logger.info("  • Нет")

        logger.info("⛔ Ошибки (детализация):")
        if stats.errors > 0:
            logger.err(f"  • Зафиксировано ошибок: {stats.errors}")
        else:
            logger.info("  • Нет")

        if stats.errors > 0:
            logger.err(f"❌ Detilda {self.version} — завершено с ошибками")
        elif stats.warnings > 0:
            logger.warn(f"⚠️ Detilda {self.version} — завершено с предупреждениями")
        else:
            logger.ok(f"✅ Detilda {self.version} — завершено успешно")
        logger.info("======================================")
