"""Utilities for making Tilda-exported images independent from Tilda lazy scripts."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from core import logger, utils

__all__ = ["ImageFixStats", "fix_project_images"]


@dataclass
class ImageFixStats:
    updated_files: int = 0
    img_tags_fixed: int = 0
    background_tags_fixed: int = 0
    unresolved_candidates: int = 0


_TAG_RE = re.compile(r"<(?P<name>[a-zA-Z][a-zA-Z0-9:-]*)(?P<attrs>[^>]*)>", re.DOTALL)
_ATTR_RE = re.compile(
    r"(?P<name>[a-zA-Z_:][a-zA-Z0-9_:\-\.]*)\s*=\s*(?P<quote>[\"'])(?P<value>.*?)(?P=quote)",
    re.DOTALL,
)
_BG_IMAGE_RE = re.compile(
    r"background-image\s*:\s*url\((?P<quote>[\"']?)(?P<url>[^\)\"']+)(?P=quote)\)",
    re.IGNORECASE,
)

_FULL_IMAGE_ATTRS = (
    "data-original",
    "data-img-zoom-url",
    "data-lazy",
    "data-lazy-src",
    "data-zoom-target",
    "data-popup-img-url",
)


def _parse_attrs(attrs_chunk: str) -> tuple[dict[str, str], list[str]]:
    attrs: dict[str, str] = {}
    order: list[str] = []
    for match in _ATTR_RE.finditer(attrs_chunk):
        name = match.group("name")
        value = match.group("value").strip()
        attrs[name] = value
        if name not in order:
            order.append(name)
    return attrs, order


def _build_tag(name: str, attrs: dict[str, str], order: list[str], self_closing: bool) -> str:
    rendered: list[str] = []
    for attr_name in order:
        if attr_name not in attrs:
            continue
        rendered.append(f'{attr_name}="{attrs[attr_name]}"')
    for attr_name, value in attrs.items():
        if attr_name in order:
            continue
        rendered.append(f'{attr_name}="{value}"')
    suffix = " />" if self_closing else ">"
    if rendered:
        return f"<{name} {' '.join(rendered)}{suffix}"
    return f"<{name}{suffix}"


def _pick_full_image(attrs: dict[str, str], current: str) -> str:
    for key in _FULL_IMAGE_ATTRS:
        value = attrs.get(key, "").strip()
        if value:
            return value
    return current


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


def _transform_html_images(text: str) -> tuple[str, int, int, int]:
    img_fixed = 0
    bg_fixed = 0
    unresolved = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal img_fixed, bg_fixed, unresolved
        name = match.group("name")
        attrs_chunk = match.group("attrs")
        original_tag = match.group(0)
        lower_name = name.lower()

        if lower_name.startswith("/"):
            return original_tag

        attrs, order = _parse_attrs(attrs_chunk)
        if not attrs:
            return original_tag

        changed = False
        full_image = _pick_full_image(attrs, attrs.get("src", "").strip())

        if lower_name == "img":
            src = attrs.get("src", "").strip()
            if full_image and src != full_image:
                attrs["src"] = full_image
                changed = True
                img_fixed += 1
            if full_image and attrs.get("srcset", "").strip() and full_image not in attrs["srcset"]:
                attrs["srcset"] = f"{full_image} 1x"
                changed = True
            for attr_name in ("data-src", "data-lazy", "data-lazy-src"):
                value = attrs.get(attr_name, "").strip()
                if value and full_image and value != full_image:
                    attrs[attr_name] = full_image
                    changed = True
            if full_image and attrs.get("src", "").strip() and attrs["src"].strip() != full_image:
                unresolved += 1

        style = attrs.get("style", "")
        if full_image and (style or any(key in attrs for key in ("data-original", "data-bgimgfield", "data-content-cover-id"))):
            new_style, style_changed = _update_background_style(style, full_image)
            if style_changed:
                attrs["style"] = new_style
                changed = True
                if lower_name != "img":
                    bg_fixed += 1

        if not changed:
            if lower_name == "img" and attrs.get("data-original") and attrs.get("src") != attrs.get("data-original"):
                unresolved += 1
            return original_tag

        self_closing = original_tag.rstrip().endswith("/>")
        return _build_tag(name, attrs, order, self_closing)

    updated = _TAG_RE.sub(_replace, text)
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

        new_text, img_fixed, bg_fixed, unresolved = _transform_html_images(text)
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
