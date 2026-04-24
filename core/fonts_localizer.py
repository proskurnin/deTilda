"""Localize Google Fonts references in project CSS files."""
from __future__ import annotations

import hashlib
import os
import re
import urllib.error
import urllib.parse
from pathlib import Path

from core import logger, utils
from core.downloader import fetch_bytes, fetch_text

__all__ = ["localize_google_fonts"]

_GOOGLE_IMPORT_RE = re.compile(
    r"@import\s+(?:url\(\s*)?[\"']?(?P<url>(?:https?:)?//fonts\.googleapis\.com/[^\s\"')]+)[\"']?\s*\)?\s*;",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"url\((?P<quote>[\"']?)(?P<url>[^)\"']+)(?P=quote)\)", re.IGNORECASE)




def _is_google_font_file(url: str) -> bool:
    normalized = url.lower().strip()
    return "fonts.gstatic.com" in normalized and normalized.split("?", 1)[0].endswith(".woff2")


def _resolve_url(base_url: str, raw_url: str) -> str:
    if raw_url.startswith("//"):
        return f"https:{raw_url}"
    return urllib.parse.urljoin(base_url, raw_url)


def _target_path(project_root: Path, url: str) -> Path:
    parsed = urllib.parse.urlsplit(url)
    original_name = Path(urllib.parse.unquote(parsed.path)).name or "font.woff2"
    stem = Path(original_name).stem
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    safe_name = f"{stem}-{digest}.woff2"
    return project_root / "fonts" / "google" / safe_name


def _replace_font_urls(
    css_text: str,
    css_path: Path,
    project_root: Path,
    download_cache: dict[str, Path],
) -> tuple[str, int]:
    downloaded = 0

    def _sub(match: re.Match[str]) -> str:
        nonlocal downloaded
        raw_url = match.group("url").strip()
        if not _is_google_font_file(raw_url):
            return match.group(0)
        absolute = _resolve_url("https://fonts.gstatic.com/", raw_url)
        destination = download_cache.get(absolute)
        if destination is None:
            destination = _target_path(project_root, absolute)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                payload = fetch_bytes(absolute)
                destination.write_bytes(payload)
                downloaded += 1
                logger.info(
                    f"🌐 Загружен Google Font: {absolute} → {utils.relpath(destination, project_root)}"
                )
            download_cache[absolute] = destination

        rel = os.path.relpath(destination, start=css_path.parent).replace('\\', '/')
        return f"url('{rel}')"

    return _URL_RE.sub(_sub, css_text), downloaded


def _inline_google_imports(
    css_text: str,
    css_path: Path,
    project_root: Path,
    download_cache: dict[str, Path],
) -> tuple[str, int, int]:
    imports_inlined = 0
    downloaded = 0

    def _sub(match: re.Match[str]) -> str:
        nonlocal imports_inlined, downloaded
        import_url = _resolve_url("https://fonts.googleapis.com/", match.group("url"))
        remote_css = fetch_text(import_url)
        localized_css, downloaded_now = _replace_font_urls(remote_css, css_path, project_root, download_cache)
        downloaded += downloaded_now
        imports_inlined += 1
        return f"/* localized from {import_url} */\n{localized_css}\n/* end localized import */"

    return _GOOGLE_IMPORT_RE.sub(_sub, css_text), imports_inlined, downloaded


def localize_google_fonts(project_root: Path) -> tuple[int, int, int]:
    """Localize Google Fonts for all CSS files.

    Returns tuple: (updated_files, inlined_imports, downloaded_fonts).
    """

    css_files = utils.list_files_recursive(project_root, extensions=(".css",))
    if not css_files:
        logger.info("[fonts] CSS файлы не найдены — пропуск локализации Google Fonts.")
        return 0, 0, 0

    download_cache: dict[str, Path] = {}
    updated_files = 0
    total_imports = 0
    total_downloaded = 0

    for css_path in css_files:
        try:
            original = utils.safe_read(css_path)
        except Exception as exc:
            logger.warn(f"[fonts] Пропуск {css_path.name}: {exc}")
            continue

        changed = original
        try:
            changed, imports_inlined, downloaded = _inline_google_imports(
                changed, css_path, project_root, download_cache
            )
            changed, downloaded_direct = _replace_font_urls(
                changed, css_path, project_root, download_cache
            )
            downloaded += downloaded_direct
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            logger.warn(f"[fonts] Не удалось локализовать шрифты в {utils.relpath(css_path, project_root)}: {exc}")
            continue
        except Exception as exc:
            logger.warn(f"[fonts] Ошибка в {utils.relpath(css_path, project_root)}: {exc}")
            continue

        if changed != original:
            utils.safe_write(css_path, changed)
            updated_files += 1
            total_imports += imports_inlined
            total_downloaded += downloaded
            logger.info(f"🔤 Локализованы шрифты в {utils.relpath(css_path, project_root)}")

    if updated_files:
        logger.info(
            f"[fonts] Обновлено CSS файлов: {updated_files}; инлайн-импортов: {total_imports}; скачано .woff2: {total_downloaded}"
        )
    else:
        logger.info("[fonts] Ссылки на Google Fonts не найдены.")

    return updated_files, total_imports, total_downloaded
