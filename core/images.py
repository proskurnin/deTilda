"""Utilities for conservative image fixes in Tilda-exported HTML."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from core import logger, utils

__all__ = ["ImageFixStats", "fix_project_images"]


@dataclass
class ImageFixStats:
    updated_files: int = 0
    img_tags_fixed: int = 0
    background_tags_fixed: int = 0
    unresolved_candidates: int = 0


_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<(?P<name>[a-zA-Z][a-zA-Z0-9:-]*)(?P<attrs>[^>]*)>", re.IGNORECASE | re.DOTALL)
_ATTR_RE = re.compile(
    r"(?P<name>[a-zA-Z_:][a-zA-Z0-9_:\-\.]*)\s*=\s*"
    r"(?P<quote>[\"'])(?P<value>.*?)(?P=quote)",
    re.IGNORECASE | re.DOTALL,
)
_BG_IMAGE_RE = re.compile(
    r"background-image\s*:\s*url\((?P<quote>[\"']?)(?P<url>[^\)\"']+)(?P=quote)\)",
    re.IGNORECASE,
)

_FULL_IMAGE_ATTRS = (
    "data-original",
    "data-img-zoom-url",
    "data-lazy-src",
    "data-content-cover-bg",
)

_PLACEHOLDER_RE = re.compile(r"(?:1x1|blank|empty|transparent|loader)\.(?:gif|png|svg)$", re.IGNORECASE)


def _parse_attrs(attrs_chunk: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in _ATTR_RE.finditer(attrs_chunk):
        name = match.group("name").lower()
        value = match.group("value").strip()
        attrs[name] = value
    return attrs


def _pick_full_image(attrs: dict[str, str], current: str) -> str:
    for key in _FULL_IMAGE_ATTRS:
        value = attrs.get(key, "").strip()
        if value:
            return value
    return current


def _local_url_exists(project_root: Path, url: str) -> bool:
    if not url:
        return False
    split = urlsplit(url)
    if split.scheme or url.startswith("//"):
        return True
    candidate = split.path.strip()
    if not candidate or candidate.startswith("data:"):
        return True
    normalized = candidate.lstrip("/")
    return (project_root / normalized).exists()


def _looks_like_placeholder(url: str) -> bool:
    if not url:
        return True
    split = urlsplit(url)
    name = Path(split.path).name
    return bool(_PLACEHOLDER_RE.search(name))


def _replace_attr_value(tag: str, attr_name: str, new_value: str) -> tuple[str, bool]:
    pattern = re.compile(
        rf'(\b{re.escape(attr_name)}\s*=\s*)(?P<quote>["\'])(?P<value>.*?)(?P=quote)',
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(tag)
    if not match:
        return tag, False
    current = match.group("value").strip()
    if current == new_value:
        return tag, False
    quote = match.group("quote")
    start, end = match.span("value")
    updated = f"{tag[:start]}{new_value}{tag[end:]}"
    return updated, True


def _update_background_style(style: str, full_image: str) -> tuple[str, bool]:
    if not style or not full_image:
        return style, False

    match = _BG_IMAGE_RE.search(style)
    if match:
        current = match.group("url").strip()
        if current == full_image:
            return style, False
        updated = _BG_IMAGE_RE.sub(f'background-image:url("{full_image}")', style, count=1)
        return updated, True

    separator = "" if style.rstrip().endswith(";") or not style.strip() else "; "
    updated = f'{style}{separator}background-image:url("{full_image}");'
    return updated, True


def _transform_html_images(text: str, project_root: Path) -> tuple[str, int, int, int]:
    img_fixed = 0
    bg_fixed = 0
    unresolved = 0

    def _replace_img(match: re.Match[str]) -> str:
        nonlocal img_fixed, bg_fixed, unresolved
        original_tag = match.group(0)
        attrs = _parse_attrs(original_tag)
        if not attrs:
            return original_tag

        src = attrs.get("src", "").strip()
        full_image = _pick_full_image(attrs, src)
        if not full_image or full_image == src:
            return original_tag
        if not _local_url_exists(project_root, full_image):
            unresolved += 1
            return original_tag
        # Keep Tilda lazyload semantics intact:
        # promote full image only for clearly placeholder/empty src.
        if src and not _looks_like_placeholder(src):
            return original_tag
        updated_tag, changed = _replace_attr_value(original_tag, "src", full_image)
        if changed:
            img_fixed += 1
            return updated_tag
        return original_tag

    updated = _IMG_TAG_RE.sub(_replace_img, text)

    def _replace_bg(match: re.Match[str]) -> str:
        nonlocal bg_fixed, unresolved
        original_tag = match.group(0)
        name = match.group("name").lower()
        if name == "img" or name.startswith("/"):
            return original_tag
        attrs = _parse_attrs(match.group("attrs"))
        style = attrs.get("style", "")
        if not style:
            return original_tag
        full_image = _pick_full_image(attrs, "")
        if not full_image:
            return original_tag
        if not _local_url_exists(project_root, full_image):
            unresolved += 1
            return original_tag
        new_style, style_changed = _update_background_style(style, full_image)
        if not style_changed:
            return original_tag
        updated_tag, changed = _replace_attr_value(original_tag, "style", new_style)
        if changed:
            bg_fixed += 1
            return updated_tag
        return original_tag

    updated = _TAG_RE.sub(_replace_bg, updated)
    return updated, img_fixed, bg_fixed, unresolved


def fix_project_images(project_root: Path) -> ImageFixStats:
    project_root = Path(project_root)
    stats = ImageFixStats()

    for path in utils.list_files_recursive(project_root, extensions=(".html", ".htm")):
        try:
            text = utils.safe_read(path)
        except Exception as exc:
            logger.warn(f"[images] Пропуск {path.name}: {exc}")
            continue

        new_text, img_fixed, bg_fixed, unresolved = _transform_html_images(text, project_root)
        stats.img_tags_fixed += img_fixed
        stats.background_tags_fixed += bg_fixed
        stats.unresolved_candidates += unresolved

        if new_text != text:
            utils.safe_write(path, new_text)
            stats.updated_files += 1
            logger.info(f"🖼 Нормализованы изображения: {utils.relpath(path, project_root)}")

    logger.info(
        "[images] Обработано файлов: %s, img исправлено: %s, bg исправлено: %s, unresolved: %s"
        % (
            stats.updated_files,
            stats.img_tags_fixed,
            stats.background_tags_fixed,
            stats.unresolved_candidates,
        )
    )
    return stats
