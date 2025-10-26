"""Asset rename and cleanup utilities."""
from __future__ import annotations

import contextlib
import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterable, Iterator, Tuple
from uuid import uuid4

from core import logger, utils
from core.config_loader import ConfigLoader, iter_section_list

if TYPE_CHECKING:  # pragma: no cover - type checking helper
    from core.project import ProjectContext

__all__ = ["AssetStats", "rename_and_cleanup_assets"]


@dataclass
class AssetStats:
    renamed: int = 0
    removed: int = 0
    downloaded: int = 0


@dataclass
class AssetResult:
    rename_map: Dict[str, str]
    stats: AssetStats


@dataclass
class ResourceCopyRule:
    source: Path
    destination: str
    originals: list[str] = field(default_factory=list)
    applied: bool = False


def _normalize_config_path(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    while normalized.startswith("/"):
        normalized = normalized[1:]
    return normalized


def _collect_lowercase_names(section: Dict[str, object], *keys: str) -> set[str]:
    return {name.lower() for name in iter_section_list(section, *keys)}


def _sanitize(name: str) -> str:
    sanitized = (
        name.replace(" ", "_")
        .replace("(", "")
        .replace(")", "")
        .replace(",", "")
        .replace("&", "and")
    )
    return re.sub(r"_+", "_", sanitized)


_RELATIVE_LINK_LOWERCASE_PATTERN = re.compile(
    r"(?<!:)(?P<prefix>(?:\./|\.\./|/|\\)+)(?P<path>[A-Za-z0-9._\-\\/]+)"
)


def _iter_links(text: str, link_patterns: Iterable[str]) -> Iterator[str]:
    for pattern in link_patterns:
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            logger.warn(f"[assets] Некорректный паттерн ссылки: {pattern}")
            continue
        for match in regex.finditer(text):
            link = match.groupdict().get("link")
            if link:
                yield link


def _lowercase_relative_links(text: str) -> tuple[str, bool]:
    def _replacement(match: re.Match[str]) -> str:
        path = match.group("path")
        lower_path = path.lower()
        if lower_path == path:
            return match.group(0)
        return f"{match.group('prefix')}{lower_path}"

    new_text, count = _RELATIVE_LINK_LOWERCASE_PATTERN.subn(_replacement, text)
    return new_text, bool(count)


def _resolve_download_target(url: str, rules: Iterable[Dict[str, object]]) -> Tuple[str, str] | None:
    parsed = urllib.parse.urlsplit(url if not url.startswith("//") else f"https:{url}")
    if parsed.scheme not in {"http", "https"}:
        return None
    filename = Path(urllib.parse.unquote(parsed.path)).name
    if not filename:
        return None
    suffix = Path(filename).suffix.lower()
    for rule in rules:
        folder = str(rule.get("folder", "")).strip().strip("/")
        if not folder:
            continue
        extensions = rule.get("extensions")
        if extensions:
            exts = {str(ext).lower() for ext in extensions if isinstance(ext, str)}
            if suffix not in exts:
                continue
        return folder, filename
    return None


_SSL_FALLBACK_CONTEXT: ssl.SSLContext | None = None


def _get_unverified_context() -> ssl.SSLContext:
    global _SSL_FALLBACK_CONTEXT
    if _SSL_FALLBACK_CONTEXT is None:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        _SSL_FALLBACK_CONTEXT = context
    return _SSL_FALLBACK_CONTEXT


def _fetch_url(url: str) -> bytes:
    normalized = url
    if url.startswith("//"):
        normalized = f"https:{url}"
    request = urllib.request.Request(
        normalized,
        headers={
            "User-Agent": "Detilda/1.0",
            "Accept": "*/*",
        },
    )
    try:
        with contextlib.closing(
            urllib.request.urlopen(request, timeout=15)  # type: ignore[arg-type]
        ) as response:
            return response.read()
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, ssl.SSLError):
            logger.warn(
                f"[assets] SSL-проверка не удалась для {normalized}, повтор с отключённой проверкой"
            )
            with contextlib.closing(
                urllib.request.urlopen(  # type: ignore[arg-type]
                    request,
                    timeout=15,
                    context=_get_unverified_context(),
                )
            ) as response:
                return response.read()
        raise
    except ssl.SSLError:
        logger.warn(
            f"[assets] SSL-проверка не удалась для {normalized}, повтор с отключённой проверкой"
        )
        with contextlib.closing(
            urllib.request.urlopen(  # type: ignore[arg-type]
                request,
                timeout=15,
                context=_get_unverified_context(),
            )
        ) as response:
            return response.read()


def _download_remote_assets(project_root: Path, loader: ConfigLoader) -> int:
    service_cfg = loader.service_files()
    remote_cfg = service_cfg.get("remote_assets", {})
    rules = remote_cfg.get("rules", [])
    if not rules:
        return 0

    patterns_cfg = loader.patterns()
    link_patterns = patterns_cfg.get("links", [])
    if not link_patterns:
        return 0

    scan_exts = remote_cfg.get("scan_extensions") or []
    if scan_exts:
        files = utils.list_files_recursive(project_root, extensions=tuple(scan_exts))
    else:
        files = utils.list_files_recursive(project_root)

    urls: set[str] = set()
    for file_path in files:
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                text = file_path.read_text(encoding="utf-8-sig")
            except Exception:
                continue
        except Exception:
            continue

        for link in _iter_links(text, link_patterns):
            if "til" not in link.lower():
                continue
            parsed = urllib.parse.urlsplit(link if not link.startswith("//") else f"https:{link}")
            if parsed.scheme not in {"http", "https"}:
                continue
            urls.add(link)

    downloaded = 0
    for url in sorted(urls):
        target = _resolve_download_target(url, rules)
        if target is None:
            continue
        folder, filename = target
        destination_dir = project_root / folder
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination_path = destination_dir / filename
        if destination_path.exists():
            continue
        try:
            payload = _fetch_url(url)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            logger.warn(f"[assets] Не удалось скачать {url}: {exc}")
            continue
        except Exception as exc:  # pragma: no cover - сетевые сбои
            logger.warn(f"[assets] Неожиданная ошибка скачивания {url}: {exc}")
            continue

        try:
            destination_path.write_bytes(payload)
        except Exception as exc:
            logger.err(f"[assets] Ошибка записи {destination_path}: {exc}")
            continue

        downloaded += 1
        logger.info(
            f"🌐 Загружен ресурс: {url} → {utils.relpath(destination_path, project_root)}"
        )

    return downloaded


def _normalize_case_enabled(service_cfg: Dict[str, object]) -> tuple[bool, set[str]]:
    normalize_cfg: Dict[str, object] = {}
    pipeline_cfg = service_cfg.get("pipeline_stages")
    if isinstance(pipeline_cfg, dict):
        raw_cfg = pipeline_cfg.get("normalize_case")
        if isinstance(raw_cfg, dict):
            normalize_cfg = raw_cfg
        elif isinstance(raw_cfg, bool):
            normalize_cfg = {"enabled": raw_cfg}

    enabled = normalize_cfg.get("enabled")
    if enabled is None:
        enabled = True
    else:
        enabled = bool(enabled)

    extensions = {
        str(ext).lower()
        for ext in normalize_cfg.get("extensions", [])
        if isinstance(ext, str)
    }
    if not extensions:
        extensions = {".html", ".htm", ".css", ".js", ".php", ".txt"}

    return enabled, extensions


def _rename_with_case_handling(path: Path, destination: Path) -> Path | None:
    """Rename *path* to *destination*, handling case-only updates safely."""

    if path == destination:
        return destination

    if destination.exists() and destination != path:
        try:
            if destination.samefile(path):
                temp_path = path.with_name(
                    f"__detilda_tmp__{uuid4().hex}{path.suffix}"
                )
                path.rename(temp_path)
                temp_path.rename(destination)
                return destination
        except (OSError, FileNotFoundError):
            pass
        return None

    try:
        path.rename(destination)
        return destination
    except OSError:
        temp_path = path.with_name(f"__detilda_tmp__{uuid4().hex}{path.suffix}")
        try:
            path.rename(temp_path)
            temp_path.rename(destination)
            return destination
        except OSError:
            if temp_path.exists():
                with contextlib.suppress(Exception):
                    temp_path.rename(path)
            return None


def _apply_case_normalization(
    project_root: Path,
    rename_map: Dict[str, str],
    stats: AssetStats,
    patterns_cfg: Dict[str, object],
    service_cfg: Dict[str, object],
) -> None:
    enabled, extensions = _normalize_case_enabled(service_cfg)
    if not enabled:
        logger.info("[assets] Нормализация регистра файлов отключена в конфиге")
        return

    text_extensions = tuple(
        str(ext).lower()
        for ext in patterns_cfg.get("text_extensions", [])
        if isinstance(ext, str)
    )
    if not text_extensions:
        text_extensions = (
            ".html",
            ".htm",
            ".css",
            ".js",
            ".php",
            ".txt",
            ".json",
            ".xml",
            ".yml",
            ".yaml",
            ".md",
            ".markdown",
            ".svg",
        )

    case_updates: Dict[str, str] = {}

    for path in sorted(project_root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in extensions:
            continue

        lower_name = path.name.lower()
        if lower_name == path.name:
            continue

        old_rel = utils.relpath(path, project_root)
        old_name = path.name
        new_path = path.with_name(lower_name)
        renamed = _rename_with_case_handling(path, new_path)
        if renamed is None:
            logger.warn(
                f"[assets] Пропуск нормализации регистра из-за конфликта: {old_rel}"
            )
            continue

        new_rel = utils.relpath(new_path, project_root)

        rename_map[old_rel] = new_rel
        rename_map[old_name] = new_path.name
        for key, value in list(rename_map.items()):
            if value == old_rel:
                rename_map[key] = new_rel
            elif value == old_name:
                rename_map[key] = new_path.name

        case_updates[old_rel] = new_rel
        case_updates[old_name] = new_path.name
        if "/" in old_rel:
            windows_old = old_rel.replace("/", "\\")
            windows_new = new_rel.replace("/", "\\")
            rename_map[windows_old] = windows_new
            case_updates[windows_old] = windows_new
            for key, value in list(rename_map.items()):
                if value == windows_old:
                    rename_map[key] = windows_new

        stats.renamed += 1
        logger.info(
            f"🔡 Приведено к нижнему регистру: {old_rel} → {new_rel}"
        )

    replacements = {
        old: new
        for old, new in case_updates.items()
        if isinstance(old, str)
        and isinstance(new, str)
        and old != new
    }
    if replacements:
        extra_replacements: Dict[str, str] = {}
        for old, new in replacements.items():
            old_root, old_ext = os.path.splitext(old)
            new_root, new_ext = os.path.splitext(new)
            if (
                old_ext
                and new_ext
                and old_ext.lower() == new_ext.lower()
                and old_root
                and new_root
                and old_root != new_root
            ):
                extra_replacements.setdefault(old_root, new_root)
        replacements.update(extra_replacements)

    replacement_patterns: list[tuple[str, str, re.Pattern[str]]] = []
    for old, new in replacements.items():
        if not old:
            continue
        pattern = re.compile(
            rf"(?P<prefix>(?:\./|\.\./|\.\\|..\\|/|\\)*){re.escape(old)}"
        )
        replacement_patterns.append((old, new, pattern))

    links_updated = False

    for file_path in utils.list_files_recursive(project_root, extensions=text_extensions):
        try:
            original_text = utils.safe_read(file_path)
        except Exception as exc:
            logger.warn(f"[assets] Пропуск обновления ссылок в {file_path.name}: {exc}")
            continue

        new_text = original_text
        changed = False
        for old, new, pattern in replacement_patterns:
            if old not in new_text:
                continue

            def _replacement(match: re.Match[str], *, _new=new) -> str:
                return f"{match.group('prefix')}{_new}"

            new_text, count = pattern.subn(_replacement, new_text)
            if count:
                changed = True

        new_text, lowered = _lowercase_relative_links(new_text)
        if lowered:
            changed = True

        if changed and new_text != original_text:
            utils.safe_write(file_path, new_text)
            links_updated = True
            logger.info(
                f"🔡 Обновлены ссылки (нижний регистр): {utils.relpath(file_path, project_root)}"
            )

    if not links_updated:
        if replacement_patterns:
            logger.info(
                "🔡 Ссылки (нижний регистр) уже соответствуют именам файлов, изменений не потребовалось"
            )
        else:
            logger.info(
                "🔡 Нормализация урлов (приведение к нижнему регистру) не потребовалась"
            )


def rename_and_cleanup_assets(
    project_root: Path | "ProjectContext",
    loader: ConfigLoader | None = None,
) -> AssetResult:
    context: ProjectContext | None = None
    if hasattr(project_root, "project_root") and not isinstance(project_root, Path):
        context = project_root  # type: ignore[assignment]
        project_root = context.project_root
        loader = context.config_loader

    if loader is None:
        raise ValueError("ConfigLoader не передан")

    project_root = Path(project_root)
    patterns_cfg = loader.patterns()
    images_cfg = loader.images()
    service_cfg = loader.service_files()

    downloaded = _download_remote_assets(project_root, loader)

    regex_pattern = (
        patterns_cfg.get("assets", {}).get("til_to_ai_filename")
        if isinstance(patterns_cfg.get("assets"), dict)
        else None
    )
    til_regex = re.compile(str(regex_pattern or r"\btil"), re.IGNORECASE)

    exclude_from_rename = _collect_lowercase_names(service_cfg, "exclude_from_rename", "files")
    delete_after_rename = _collect_lowercase_names(images_cfg, "delete_physical_files", "after_rename")
    delete_immediately = _collect_lowercase_names(images_cfg, "delete_physical_files", "as_is")
    delete_service = _collect_lowercase_names(service_cfg, "scripts_to_delete", "after_rename")

    resource_cfg = service_cfg.get("resource_copy", {})
    resource_rules: list[ResourceCopyRule] = []
    resource_lookup: dict[str, ResourceCopyRule] = {}
    resource_name_lookup: dict[str, ResourceCopyRule] = {}
    resources_dir = loader.base_dir / "resources"
    for entry in resource_cfg.get("files", []) if isinstance(resource_cfg, dict) else []:
        if not isinstance(entry, dict):
            continue
        source_name = str(entry.get("source", "")).strip()
        destination_name = str(entry.get("destination", entry.get("target", ""))).strip()
        if not source_name or not destination_name:
            continue
        originals_values = entry.get("originals", [])
        originals: list[str] = []
        if isinstance(originals_values, (list, tuple)):
            for original in originals_values:
                if not isinstance(original, str):
                    continue
                normalized = _normalize_config_path(original)
                if not normalized:
                    continue
                originals.append(normalized)
        destination = _normalize_config_path(destination_name) or Path(destination_name).name
        rule = ResourceCopyRule(
            source=resources_dir / source_name,
            destination=destination,
            originals=originals,
        )
        resource_rules.append(rule)
        for original in originals:
            resource_lookup[original.lower()] = rule
            resource_name_lookup[Path(original).name.lower()] = rule

    def _handle_resource_replacement(path: Path, relative: str) -> bool:
        normalized_relative = _normalize_config_path(relative)
        rule = resource_lookup.get(normalized_relative.lower()) or resource_name_lookup.get(
            path.name.lower()
        )
        if not rule:
            return False
        try:
            path.unlink()
        except Exception as exc:
            logger.err(f"[assets] Ошибка удаления {path}: {exc}")
            return False
        rule.applied = True
        stats.removed += 1
        rename_map[normalized_relative or path.name] = rule.destination
        logger.info(
            f"🧩 Заменён ресурс: {normalized_relative or path.name} → {rule.destination}"
        )
        return True

    rename_map: Dict[str, str] = {}
    stats = AssetStats(downloaded=downloaded)

    for path in sorted(project_root.rglob("*")):
        if not path.is_file():
            continue

        name_lower = path.name.lower()
        relative_path = utils.relpath(path, project_root)

        if _handle_resource_replacement(path, relative_path):
            continue

        if name_lower in delete_immediately or name_lower in delete_service:
            try:
                path.unlink()
                stats.removed += 1
                logger.info(f"🗑 Удалён (as_is): {path.name}")
            except Exception as exc:
                logger.err(f"[assets] Ошибка удаления {path}: {exc}")
            continue

        if name_lower in exclude_from_rename:
            continue

        new_name = path.name
        match = til_regex.search(path.stem)
        if match:
            new_name = _sanitize(til_regex.sub("ai", path.stem, count=1) + path.suffix)

        if new_name != path.name:
            new_path = path.with_name(new_name)
            try:
                old_rel = utils.relpath(path, project_root)
                path = path.rename(new_path)
                new_rel = utils.relpath(new_path, project_root)
                rename_map[old_rel] = new_rel
                stats.renamed += 1
                logger.info(f"🔄 Переименован: {old_rel} → {new_rel}")
                name_lower = new_path.name.lower()
            except Exception as exc:
                logger.err(f"[assets] Ошибка переименования {path}: {exc}")
                continue

        if name_lower in delete_after_rename or name_lower in delete_service:
            try:
                path.unlink()
                stats.removed += 1
                logger.info(f"🗑 Удалён (after_rename): {path.name}")
            except Exception as exc:
                logger.err(f"[assets] Ошибка удаления {path}: {exc}")

    placeholder = project_root / "images" / "1px.png"
    if not placeholder.exists():
        placeholder.parent.mkdir(parents=True, exist_ok=True)
        placeholder.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc``\x00\x00"
            b"\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        logger.info(f"🧩 Добавлен placeholder: {utils.relpath(placeholder, project_root)}")

    mapping_cfg = service_cfg.get("rename_map_output", {})
    project_name = logger.get_project_name()
    mapping_name_template = mapping_cfg.get("filename")

    if mapping_name_template:
        try:
            mapping_name = mapping_name_template.format(project=project_name)
        except Exception:
            mapping_name = mapping_name_template
    else:
        mapping_name = f"{project_name}_rename_map.json"

    if mapping_name == "rename_map.json":
        mapping_name = f"{project_name}_rename_map.json"
    mapping_location = str(mapping_cfg.get("location", "logs")).strip()
    if mapping_location.lower() == "logs":
        mapping_dir = logger.get_logs_dir()
    else:
        mapping_dir = project_root / mapping_location
    mapping_path = mapping_dir / mapping_name

    legacy_candidates = [project_root / "rename_map.json", mapping_dir / "rename_map.json"]
    for legacy_mapping in legacy_candidates:
        if legacy_mapping.exists():
            try:
                legacy_mapping.unlink()
            except Exception as exc:
                logger.warn(
                    f"[assets] Не удалось удалить устаревший rename_map.json: {exc}"
                )

    _apply_case_normalization(project_root, rename_map, stats, patterns_cfg, service_cfg)

    for rule in resource_rules:
        destination_path = project_root / rule.destination
        try:
            if not rule.source.exists():
                logger.warn(
                    f"[assets] Ресурс для копирования не найден: {rule.source}"  # pragma: no cover
                )
            else:
                utils.safe_copy(rule.source, destination_path)
        except Exception as exc:
            logger.err(f"[assets] Ошибка копирования {rule.source} → {destination_path}: {exc}")
        for original in rule.originals:
            rename_map.setdefault(original, rule.destination)

    try:
        utils.safe_write(
            mapping_path,
            json.dumps(rename_map, ensure_ascii=False, indent=2, sort_keys=True),
        )
        relative_mapping = utils.relpath(mapping_path, logger.get_logs_dir())
        logger.ok(
            f"💾 Таблица маппинга сохранена: {relative_mapping} ({len(rename_map)} элементов)"
        )
    except Exception as exc:
        logger.err(f"[assets] Ошибка сохранения {mapping_path.name}: {exc}")

    logger.info(
        f"📦 Ассеты обработаны: переименовано {stats.renamed}, удалено {stats.removed}"
    )
    if stats.downloaded:
        logger.info(f"🌐 Загружено удалённых ассетов: {stats.downloaded}")

    if context is not None:
        context.update_rename_map(rename_map)

    return AssetResult(rename_map=rename_map, stats=stats)
