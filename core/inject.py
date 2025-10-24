# -*- coding: utf-8 -*-
"""HTML injection helpers built on top of the configuration facade."""
from __future__ import annotations

import re

from core import logger, utils
from core.project import ProjectContext


class HtmlInjector:
    def __init__(self, context: ProjectContext) -> None:
        self.context = context
        service_cfg = context.config_loader.service_files
        self._inject_opts = service_cfg.as_dict().get("html_inject_options", {}) or {}
        self._scripts_to_comment = list(
            service_cfg.as_dict()
            .get("scripts_to_comment_out_tags", {})
            .get("filenames", [])
        )

    @property
    def handler_name(self) -> str:
        return str(self._inject_opts.get("inject_handler_script", "form-handler.js"))

    @property
    def injection_marker(self) -> str:
        return str(self._inject_opts.get("inject_after_marker", "</body>"))

    def _comment_scripts(self, content: str) -> str:
        for script in self._scripts_to_comment:
            pattern = rf"(<script[^>]+{re.escape(script)}[^>]*></script>)"
            content = re.sub(pattern, r"<!-- \1 -->", content, flags=re.IGNORECASE)
        return content

    def _inject_block(self, content: str, script_name: str) -> str:
        marker = self.injection_marker
        script_tag = f'\n<script src="js/{script_name}"></script>\n'
        pattern = re.compile(re.escape(marker), re.IGNORECASE)
        if pattern.search(content):
            return pattern.sub(script_tag + marker, content)
        return content + script_tag

    def inject(self) -> int:
        processed = 0
        handler = self.handler_name
        marker = self.injection_marker

        for path in self.context.project_root.rglob("*.html"):
            try:
                content = utils.safe_read(path)
            except Exception as exc:
                logger.warn(f"[inject] Пропуск {path.name}: {exc}")
                continue

            original = content
            content = self._comment_scripts(content)

            if handler not in content:
                content = self._inject_block(content, handler)
                logger.info(f"🧩 Добавлен скрипт {handler} в {path.name}")

            if "aida-forms-1.0.min.js" not in content:
                content = self._inject_block(content, "aida-forms-1.0.min.js")
                logger.info(f"🧩 Добавлен AIDA forms в {path.name}")

            if content != original:
                utils.safe_write(path, content)
                processed += 1

        logger.info(
            f"✓ Внедрение завершено. Обновлено файлов: {processed} (маркер: {marker})."
        )
        return processed


def inject_form_scripts(context: ProjectContext) -> int:
    injector = HtmlInjector(context)
    return injector.inject()
