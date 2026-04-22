"""Utilities for conservative post-processing of images/styles in exported HTML."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from core import logger, utils

__all__ = [
    "ImageFixStats",
    "fix_project_images",
    "is_preview_or_placeholder_asset",
    "normalize_background_image_from_data_original",
    "normalize_inline_backgrounds",
    "normalize_img_src_from_data_original",
]


@dataclass
class ImageFixStats:
    updated_files: int = 0
    img_tags_fixed: int = 0
    background_tags_fixed: int = 0
    unresolved_candidates: int = 0


_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE | re.DOTALL)
_ATTR_RE = re.compile(
    r"(?P<name>[a-zA-Z_:][a-zA-Z0-9_:\-\.]*)\s*=\s*"
    r"(?P<quote>[\"'])(?P<value>.*?)(?P=quote)",
    re.IGNORECASE | re.DOTALL,
)
_INLINE_BG_URL_RE = re.compile(
    r"(?P<prop>background(?:-image)?)\s*:\s*url\(\s*\"(?P<url>[^\"]+)\"\s*\)",
    re.IGNORECASE,
)
_STYLE_BG_URL_RE = re.compile(
    r"(?P<prefix>background(?:-image)?\s*:\s*url\(\s*)(?P<quote>['\"]?)(?P<url>[^)\"']+)(?P=quote)(?P<suffix>\s*\))",
    re.IGNORECASE,
)
_PLACEHOLDER_RE = re.compile(
    r"(?:"
    r"_-_empty_|"
    r"1px\.png|"
    r"1x1\.(?:gif|png|svg)|"
    r"spinner|"
    r"resize_20x|"
    r"resizeb_20x|"
    r"logo404|"
    r"blank\.(?:gif|png|svg)|"
    r"empty\.(?:gif|png|svg)|"
    r"transparent\.(?:gif|png|svg)|"
    r"loader\.(?:gif|png|svg)"
    r")",
    re.IGNORECASE,
)


def _parse_attrs(attrs_chunk: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in _ATTR_RE.finditer(attrs_chunk):
        name = match.group("name").lower()
        value = match.group("value").strip()
        attrs[name] = value
    return attrs


def _local_url_exists(project_root: Path, url: str) -> bool:
    if not url:
        return False
    split = urlsplit(url)
    if split.scheme or url.startswith("//"):
        return False
    candidate = split.path.strip()
    if not candidate or candidate.startswith("data:"):
        return False
    normalized = candidate.lstrip("/")
    return (project_root / normalized).exists()


def _is_external_url(url: str) -> bool:
    split = urlsplit(url.strip())
    return bool(split.scheme) or url.strip().startswith("//")


def _looks_like_placeholder(url: str) -> bool:
    if not url:
        return True
    split = urlsplit(url)
    name = Path(split.path).name
    return bool(_PLACEHOLDER_RE.search(name) or _PLACEHOLDER_RE.search(split.path))


def is_preview_or_placeholder_asset(url: str) -> bool:
    """Return ``True`` for placeholder/preview image URLs used by lazy runtime."""

    return _looks_like_placeholder(url)


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
    start, end = match.span("value")
    updated = f"{tag[:start]}{new_value}{tag[end:]}"
    return updated, True


def normalize_inline_backgrounds(text: str) -> tuple[str, int]:
    """Normalize inline background/background-image url(\"...\") to url('...')."""
    fixed = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal fixed
        fixed += 1
        prop = match.group("prop")
        url = match.group("url").strip()
        return f"{prop}:url('{url}')"

    updated = _INLINE_BG_URL_RE.sub(_replace, text)
    return updated, fixed


def normalize_img_src_from_data_original(text: str, project_root: Path) -> tuple[str, int, int]:
    """Promote ``data-original`` to ``src`` only for placeholder/empty image sources."""
    img_fixed = 0
    unresolved = 0

    def _replace_img(match: re.Match[str]) -> str:
        nonlocal img_fixed, unresolved
        original_tag = match.group(0)
        attrs = _parse_attrs(original_tag)
        if not attrs:
            return original_tag

        src = attrs.get("src", "").strip()
        data_original = attrs.get("data-original", "").strip()
        if not data_original:
            return original_tag
        if src and _is_external_url(src):
            return original_tag
        if src and not _looks_like_placeholder(src):
            return original_tag
        if not _local_url_exists(project_root, data_original):
            unresolved += 1
            return original_tag
        updated_tag, changed = _replace_attr_value(original_tag, "src", data_original)
        if changed:
            img_fixed += 1
            return updated_tag
        return original_tag

    updated = _IMG_TAG_RE.sub(_replace_img, text)
    return updated, img_fixed, unresolved


def normalize_background_image_from_data_original(
    text: str, project_root: Path
) -> tuple[str, int, int]:
    """Promote ``data-original`` into inline ``background-image`` for preview backgrounds."""

    background_fixed = 0
    unresolved = 0

    def _replace_tag(match: re.Match[str]) -> str:
        nonlocal background_fixed, unresolved
        original_tag = match.group(0)
        attrs = _parse_attrs(original_tag)
        if not attrs:
            return original_tag

        data_original = attrs.get("data-original", "").strip()
        style_value = attrs.get("style", "").strip()
        if not data_original or not style_value:
            return original_tag
        if not _local_url_exists(project_root, data_original):
            unresolved += 1
            return original_tag

        style_match = _STYLE_BG_URL_RE.search(style_value)
        if not style_match:
            return original_tag

        current_url = style_match.group("url").strip()
        if not current_url:
            return original_tag
        if _is_external_url(current_url):
            return original_tag
        if not is_preview_or_placeholder_asset(current_url):
            return original_tag

        updated_style = (
            f"{style_value[:style_match.start('url')]}"
            f"{data_original}"
            f"{style_value[style_match.end('url'):]}"
        )
        style_tag, changed = _replace_attr_value(original_tag, "style", updated_style)
        if changed:
            background_fixed += 1
            return style_tag
        return original_tag

    updated = re.sub(r"<[a-zA-Z][^>]*>", _replace_tag, text)
    return updated, background_fixed, unresolved


def _transform_html_images(text: str, project_root: Path) -> tuple[str, int, int, int]:
    updated, inline_bg_fixed = normalize_inline_backgrounds(text)
    updated, img_fixed, unresolved_img = normalize_img_src_from_data_original(updated, project_root)
    updated, bg_fixed, unresolved_bg = normalize_background_image_from_data_original(updated, project_root)
    return updated, img_fixed, inline_bg_fixed + bg_fixed, unresolved_img + unresolved_bg


def _should_process_file(path: Path) -> bool:
    lower_name = path.name.lower()
    if lower_name.endswith((".html", ".htm")):
        return True
    return "files" in {part.lower() for part in path.parts} and lower_name.endswith("body.html")


def fix_project_images(project_root: Path) -> ImageFixStats:
    project_root = Path(project_root)
    stats = ImageFixStats()

    for path in utils.list_files_recursive(project_root, extensions=(".html", ".htm")):
        if not _should_process_file(path):
            continue
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
