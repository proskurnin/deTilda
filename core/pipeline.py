"""High level orchestration for the deTilda toolchain."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from core import (
    archive,
    assets,
    cdn_localizer,
    checker,
    cleaners,
    font_substitute,
    forms,
    fonts_localizer,
    html_prettify,
    images,
    inject,
    logger,
    page404,
    refs,
    report,
    script_cleaner,
)
from core.project import ProjectContext
from core.version import APP_VERSION


@dataclass
class PipelineStats:
    renamed_assets: int = 0
    removed_assets: int = 0
    cleaned_files: int = 0
    fixed_links: int = 0
    broken_links: int = 0
    htaccess_routes_initially_broken: int = 0
    htaccess_routes_autofixed: int = 0
    broken_htaccess_routes: int = 0
    ssl_bypassed_downloads: int = 0
    warnings: int = 0
    errors: int = 0
    downloaded_remote_assets: int = 0
    forms_found: int = 0
    forms_hooked: int = 0
    formatted_html_files: int = 0
    html_prettify_skipped: bool = False
    images_updated_files: int = 0
    images_img_fixed: int = 0
    images_background_fixed: int = 0
    images_unresolved: int = 0
    exec_time: float = 0.0


class DetildaPipeline:
    def __init__(self, version: str = APP_VERSION, logs_dir: Path | None = None) -> None:
        self.version = version
        self.logs_dir = logs_dir

    def run(self, archive_path: Path) -> PipelineStats:
        start_time = time.time()

        project_root = archive.unpack_archive(archive_path)
        if not project_root:
            raise RuntimeError("Не удалось распаковать архив")

        context = ProjectContext.from_project_root(project_root)
        context.attach_logger(logs_dir=self.logs_dir)

        try:
            logger.info(f"=== deTilda {self.version} ===")
            logger.info(f"Рабочая папка: {archive_path.parent.resolve()}")
            logger.info(f"Дата запуска: {time.strftime('%Y-%m-%d %H:%M:%S')}")

            stats = PipelineStats()

            with logger.module_scope("assets"):
                asset_result = assets.rename_and_cleanup_assets(context)
            stats.renamed_assets = asset_result.stats.renamed
            stats.removed_assets = asset_result.stats.removed
            stats.downloaded_remote_assets = asset_result.stats.downloaded
            stats.ssl_bypassed_downloads = asset_result.stats.ssl_bypassed_downloads
            stats.warnings += asset_result.stats.warnings
            report.generate_intermediate_report(stats.renamed_assets, 0, 0, 0)

            with logger.module_scope("page404"):
                page404.update_404_page(context.project_root)

            with logger.module_scope("cleaners"):
                clean_result = cleaners.clean_project_files(context, context.rename_map)
            stats.cleaned_files = clean_result.updated
            stats.removed_assets += clean_result.removed
            report.generate_intermediate_report(stats.renamed_assets, stats.cleaned_files, 0, 0)

            with logger.module_scope("forms"):
                forms.generate_send_email_php(context)
            with logger.module_scope("inject"):
                stats.forms_hooked = inject.inject_form_scripts(context)

            with logger.module_scope("font_substitute"):
                font_substitute.substitute_tilda_fonts(context.project_root)

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

            with logger.module_scope("cdn_localizer"):
                cdn_result = cdn_localizer.localize_cdn_urls(context.project_root)
            stats.warnings += cdn_result.download_failures

            with logger.module_scope("cdn_cleanup"):
                cdn_localizer.cleanup_unresolved_cdn_references(context.project_root)

            with logger.module_scope("images"):
                image_fix = images.fix_project_images(context.project_root)
            stats.images_updated_files = image_fix.updated_files
            stats.images_img_fixed = image_fix.img_tags_fixed
            stats.images_background_fixed = image_fix.background_tags_fixed
            stats.images_unresolved = image_fix.unresolved_candidates
            stats.warnings += image_fix.unresolved_candidates

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

            with logger.module_scope("html_prettify"):
                html_prettify.run(context, stats=stats)

            with logger.module_scope("checker"):
                link_check = checker.check_links(context.project_root, context.config_loader)
            htaccess_missing = link_check.htaccess_result.missing_routes if link_check.htaccess_result else []
            stats.broken_htaccess_routes = sum(1 for r in htaccess_missing if r.action == "unresolved")
            stats.broken_links += link_check.broken
            stats.warnings += link_check.broken
            stats.warnings += stats.broken_htaccess_routes

            with logger.module_scope("tilda-remnants"):
                remnants = checker.check_tilda_remnants(context.project_root, context.config_loader)
            stats.warnings += remnants.total_occurrences

            stats.exec_time = time.time() - start_time
            with logger.module_scope("report"):
                report.generate_final_report(
                    project_root=context.project_root,
                    cleaned_count=stats.cleaned_files,
                    renamed_count=stats.renamed_assets,
                    formatted_html_files=stats.formatted_html_files,
                    warnings=stats.warnings,
                    errors=stats.errors,
                    broken_links_fixed=stats.fixed_links,
                    broken_links_left=stats.broken_links,
                    htaccess_routes_initially_broken=stats.htaccess_routes_initially_broken,
                    htaccess_routes_autofixed=stats.htaccess_routes_autofixed,
                    broken_htaccess_routes=stats.broken_htaccess_routes,
                    downloaded_remote_assets=stats.downloaded_remote_assets,
                    ssl_bypass_downloads=stats.ssl_bypassed_downloads,
                    forms_found=stats.forms_found,
                    forms_hooked=stats.forms_hooked,
                    tilda_remnants=remnants.total_occurrences,
                    missing_htaccess_routes=htaccess_missing,
                    exec_time=stats.exec_time,
                )

            self._print_final_summary(stats, stats.exec_time)

            return stats
        finally:
            logger.close()

    def _print_final_summary(self, stats: PipelineStats, elapsed_seconds: float) -> None:
        logger.info("======================================")
        effective_warnings = stats.warnings
        effective_errors = stats.errors
        status_message = self._status_message(stats)
        logger.info(f"🎯  deTilda {self.version} — {status_message}")
        logger.info(f"📦 Переименовано ассетов: {stats.renamed_assets}")
        logger.info(f"🗑 Удалено ассетов: {stats.removed_assets}")
        logger.info(f"🧹 Очищено файлов: {stats.cleaned_files}")
        logger.info(f"🧼 Отформатировано HTML-файлов: {stats.formatted_html_files}")
        logger.info(f"🌐 Загружено удалённых ассетов: {stats.downloaded_remote_assets}")
        logger.info(f"🔐 SSL bypass downloads: {stats.ssl_bypassed_downloads}")
        logger.info(f"🔗 Исправлено ссылок: {stats.fixed_links}")
        logger.info(f"❌ Битых внутренних ссылок: {stats.broken_links}")
        logger.info(
            f"❌ Битых htaccess-маршрутов найдено изначально: {stats.htaccess_routes_initially_broken}"
        )
        logger.info(f"🛠 Автоисправлено htaccess-маршрутов: {stats.htaccess_routes_autofixed}")
        logger.info(f"❌ Битых htaccess-маршрутов: {stats.broken_htaccess_routes}")
        logger.info(f"📝 Форм найдено: {stats.forms_found}")
        logger.info(f"🧩 Форм подключено к handler: {stats.forms_hooked}")
        logger.info(f"🖼 Файлов с правками изображений: {stats.images_updated_files}")
        logger.info(f"🖼 Исправлено <img>: {stats.images_img_fixed}")
        logger.info(f"🖼 Исправлено background-image: {stats.images_background_fixed}")
        logger.info(f"⚠️ Потенциально неразрешённых изображений: {stats.images_unresolved}")
        logger.info(f"⚠️ Предупреждений: {stats.warnings}")
        logger.info(f"⛔ Ошибок: {stats.errors}")
        logger.info(f"🕓 Время выполнения: {elapsed_seconds:.2f} сек")
        if stats.html_prettify_skipped:
            logger.warn("⚠️ html_prettify пропущен из-за отсутствующей зависимости")

        if effective_errors > 0:
            logger.err(f"❌ deTilda {self.version} — завершено с ошибками")
        elif effective_warnings > 0:
            logger.warn(f"⚠️ deTilda {self.version} — завершено с предупреждениями")
        else:
            logger.ok(f"✅ deTilda {self.version} — завершено успешно")

        critical_findings: list[str] = []
        if stats.broken_htaccess_routes > 0:
            critical_findings.append(
                f"Broken htaccess routes: {stats.broken_htaccess_routes}"
            )
        if stats.ssl_bypassed_downloads > 0:
            critical_findings.append(
                f"SSL bypass used for downloads: {stats.ssl_bypassed_downloads}"
            )
        if critical_findings:
            logger.warn("CRITICAL FINDINGS:")
            for idx, finding in enumerate(critical_findings, start=1):
                logger.warn(f"{idx}. {finding}")
        logger.info("======================================")

    @staticmethod
    def _status_message(stats: PipelineStats) -> str:
        if stats.html_prettify_skipped and stats.warnings == 0 and stats.errors == 0:
            return "завершено с предупреждениями"
        if stats.errors > 0:
            return "завершено с ошибками"
        if stats.warnings > 0:
            return "завершено с предупреждениями"
        return "завершено успешно"

