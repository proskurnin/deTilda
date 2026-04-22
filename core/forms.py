"""Helpers for generating form related assets."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from core import logger, utils
from core.module_versions import register_module_version

register_module_version(
    __name__,
    "v4.7 Stable",
    "Добавлена регистрация версий модулей для отслеживания эволюции форм.",
)

__all__ = ["generate_send_email_php", "generate_form_handler_js"]




def _resolve_project_root(project_root: Path | Any) -> Path:
    """Return the actual project root path from different inputs."""

    if hasattr(project_root, "project_root"):
        return Path(getattr(project_root, "project_root"))
    return Path(project_root)


def _extract_project_name(project_root: Path) -> str:
    """Derive project name using robots.txt Host if available."""

    robots_path = project_root / "robots.txt"
    if robots_path.exists():
        try:
            robots_content = robots_path.read_text(encoding="utf-8")
        except OSError:
            robots_content = ""

        for raw_line in robots_content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("host:"):
                host_value = line.split(":", 1)[1].strip()
                parsed = urlparse(host_value)
                host = parsed.netloc or parsed.path
                host = host.rstrip("/")
                if host:
                    return host

    return project_root.name


def generate_send_email_php(project_root: Path | Any) -> Path:
    project_root = _resolve_project_root(project_root)
    target = project_root / "send_email.php"
    template_path = Path(__file__).resolve().parent.parent / "resources" / "send_email.php"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(template_path.read_bytes())
    logger.info(f"📨 Файл send_email.php создан: {utils.relpath(target, project_root)}")
    generate_form_handler_js(project_root)
    return target


def generate_form_handler_js(project_root: Path | Any) -> Path:
    project_root = _resolve_project_root(project_root)
    target = project_root / "js" / "form-handler.js"
    template_path = Path(__file__).resolve().parent.parent / "resources" / "js" / "form-handler.js"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(template_path.read_bytes())
    logger.info(
        f"📨 Файл form-handler.js создан: {utils.relpath(target, project_root)}"
    )
    return target
