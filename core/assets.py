"""Asset rename and cleanup utilities for the deTilda pipeline.

Шаг 1 конвейера — самый объёмный. Выполняет четыре задачи:

  1. Скачивание удалённых ресурсов с CDN Tilda (CSS, JS, изображения)
  2. Удаление мусорных файлов Tilda (tildacopy.png, скрипты статистики и др.)
  3. Переименование файлов: til→ai в именах (tildablock → aidablock)
  4. Нормализация регистра: все имена файлов приводятся к нижнему регистру

Результат — AssetResult с:
  - rename_map: {старый_путь: новый_путь} — используется в refs.py для обновления ссылок
  - stats: счётчики переименований, удалений, загрузок
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import urllib.error
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterable, Iterator
from uuid import uuid4

from core import logger, utils
from core.config_loader import ConfigLoader
from core.downloader import fetch_bytes, resolve_download_folder
from core.runtime_scripts import filter_removable_scripts

if TYPE_CHECKING:  # pragma: no cover - type checking helper
    from core.project import ProjectContext

__all__ = ["AssetStats", "rename_and_cleanup_assets"]


@dataclass
class AssetStats:
    renamed: int = 0
    removed: int = 0
    downloaded: int = 0
    warnings: int = 0
    ssl_bypassed_downloads: int = 0


@dataclass
class AssetResult:
    rename_map: Dict[str, str]
    stats: AssetStats


@dataclass
class ResourceCopyRule:
    source: Path
    destination: str
    originals: list[str] = field(default_factory=list)


def _normalize_config_path(value: str) -> str:
    """Нормализует путь из конфига: убирает ./ и ведущие слеши."""
    normalized = value.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    while normalized.startswith("/"):
        normalized = normalized[1:]
    return normalized


def _sanitize(name: str) -> str:
    """Очищает имя файла: убирает спецсимволы, схлопывает множественные подчёркивания."""
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




def _download_remote_assets(project_root: Path, loader: ConfigLoader) -> tuple[int, int, int]:
    remote_cfg = loader.service_files().remote_assets
    rules_raw = [{"folder": r.folder, "extensions": list(r.extensions)} for r in remote_cfg.rules]
    if not rules_raw:
        return 0, 0, 0

    link_patterns = loader.patterns().links
    if not link_patterns:
        return 0, 0, 0

    scan_exts = remote_cfg.scan_extensions or []
    if scan_exts:
        files = utils.list_files_recursive(project_root, extensions=tuple(scan_exts))
    else:
        files = utils.list_files_recursive(project_root)

    urls: set[str] = set()
    for file_path in files:
        try:
            text = utils.safe_read(file_path)
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
    warnings = 0
    ssl_bypassed_downloads = 0
    for url in sorted(urls):
        result = resolve_download_folder(url, rules_raw)
        if result is None:
            continue
        folder, filename = result
        destination_path = project_root / folder / filename
        if destination_path.exists():
            continue
        try:
            payload, used_insecure_retry = fetch_bytes(url)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            logger.warn(f"[assets] Не удалось скачать {url}: {exc}")
            continue
        except Exception as exc:  # pragma: no cover
            logger.warn(f"[assets] Неожиданная ошибка скачивания {url}: {exc}")
            continue

        if used_insecure_retry:
            warnings += 1
            ssl_bypassed_downloads += 1

        try:
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            destination_path.write_bytes(payload)
        except Exception as exc:
            logger.err(f"[assets] Ошибка записи {destination_path}: {exc}")
            continue

        downloaded += 1
        logger.info(
            f"🌐 Загружен ресурс: {url} → {utils.relpath(destination_path, project_root)}"
        )

    return downloaded, warnings, ssl_bypassed_downloads


def _normalize_case_enabled(service_cfg: object) -> tuple[bool, set[str]]:
    """Читает настройки нормализации регистра из ServiceFilesConfig."""
    normalize_cfg = service_cfg.pipeline_stages.normalize_case  # type: ignore[union-attr]
    enabled = normalize_cfg.enabled
    extensions = {ext.lower() for ext in normalize_cfg.extensions if isinstance(ext, str)}
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
    patterns_cfg: object,
    service_cfg: object,
) -> None:
    """Приводит имена файлов к нижнему регистру и обновляет ссылки в текстовых файлах.

    macOS нечувствительна к регистру, поэтому переименование через temp-файл.
    После переименования обновляет все ссылки на эти файлы в HTML/CSS/JS.
    """
    enabled, extensions = _normalize_case_enabled(service_cfg)
    if not enabled:
        logger.info("[assets] Нормализация регистра файлов отключена в конфиге")
        return

    text_extensions = tuple(
        ext.lower() for ext in patterns_cfg.text_extensions  # type: ignore[union-attr]
        if isinstance(ext, str)
    )
    if not text_extensions:
        text_extensions = (".html", ".htm", ".css", ".js", ".php", ".txt")

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
    """Основная функция шага 1 конвейера.

    Принимает ProjectContext или Path+ConfigLoader (для обратной совместимости).
    Возвращает AssetResult с rename_map и статистикой.

    Порядок обработки каждого файла:
      1. Если файл — замена ресурса (favicon.ico, ga.js) → удалить старый, добавить в rename_map
      2. Если файл — мусор Tilda (tildacopy.png, скрипты) → удалить
      3. Если файл в exclude_from_rename (robots.txt, .htaccess) → пропустить
      4. Если имя содержит 'til' → переименовать (til→ai)
      5. После переименования: если файл — Tilda-скрипт → удалить
    """
    context: ProjectContext | None = None
    if hasattr(project_root, "project_root") and not isinstance(project_root, Path):
        # Принят ProjectContext — извлекаем из него нужные объекты
        context = project_root  # type: ignore[assignment]
        project_root = context.project_root
        loader = context.config_loader

    if loader is None:
        raise ValueError("ConfigLoader не передан")

    project_root = Path(project_root)
    patterns_cfg = loader.patterns()
    images_cfg = loader.images()
    service_cfg = loader.service_files()

    downloaded, download_warnings, ssl_bypassed_downloads = _download_remote_assets(
        project_root, loader
    )

    til_regex = re.compile(
        str(patterns_cfg.assets.til_to_ai_filename or r"\btil"), re.IGNORECASE
    )

    exclude_from_rename = {f.lower() for f in service_cfg.exclude_from_rename.files}
    delete_immediately = {f.lower() for f in images_cfg.delete_physical_files.as_is}
    delete_service_raw = list(service_cfg.scripts_to_delete.files)
    removable_service_scripts, preserved_service_scripts = filter_removable_scripts(
        delete_service_raw,
        project_root,
    )
    if preserved_service_scripts:
        logger.info(
            "[assets] Обнаружены видео/галереи/lazyload-маркеры — runtime-скрипты не удаляются: "
            + ", ".join(sorted(set(preserved_service_scripts)))
        )
    delete_service = {name.lower() for name in removable_service_scripts}

    resource_rules: list[ResourceCopyRule] = []
    resource_lookup: dict[str, ResourceCopyRule] = {}
    resource_name_lookup: dict[str, ResourceCopyRule] = {}
    resources_dir = loader.base_dir / "resources"
    for item in service_cfg.resource_copy.files:
        if not item.source or not item.destination:
            continue
        originals = [_normalize_config_path(o) for o in item.originals if o]
        destination = _normalize_config_path(item.destination) or Path(item.destination).name
        rule = ResourceCopyRule(
            source=resources_dir / item.source,
            destination=destination,
            originals=originals,
        )
        resource_rules.append(rule)
        for original in originals:
            resource_lookup[original.lower()] = rule
            resource_name_lookup[Path(original).name.lower()] = rule

    rename_map: Dict[str, str] = {}
    stats = AssetStats(
        downloaded=downloaded,
        warnings=download_warnings,
        ssl_bypassed_downloads=ssl_bypassed_downloads,
    )

    def _handle_resource_replacement(
        path: Path, relative: str, rename_map: Dict[str, str], stats: AssetStats
    ) -> bool:
        """Проверяет заменяемые ресурсы (favicon.ico, ga.js).

        Удаляет Tilda-версию файла и добавляет запись в rename_map
        чтобы refs.py обновил ссылки на новый путь.
        """
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
        stats.removed += 1
        rename_map[normalized_relative or path.name] = rule.destination
        logger.info(
            f"🧩 Заменён ресурс: {normalized_relative or path.name} → {rule.destination}"
        )
        return True

    # Главный цикл: обходим все файлы проекта в алфавитном порядке
    for path in sorted(project_root.rglob("*")):
        if not path.is_file():
            continue

        name_lower = path.name.lower()
        relative_path = utils.relpath(path, project_root)

        # Шаг 1: замена ресурса (favicon.ico, ga.js) → удалить Tilda-версию, запомнить в rename_map
        if _handle_resource_replacement(path, relative_path, rename_map, stats):
            continue

        # Шаг 2: немедленное удаление мусора (tildacopy.png, Tilda-скрипты и др.)
        if name_lower in delete_immediately or name_lower in delete_service:
            try:
                path.unlink()
                stats.removed += 1
                logger.info(f"🗑 Удалён (as_is): {path.name}")
            except Exception as exc:
                logger.err(f"[assets] Ошибка удаления {path}: {exc}")
            continue

        # Шаг 3: защищённые файлы не переименовываем (robots.txt, .htaccess, send_email.php)
        if name_lower in exclude_from_rename:
            continue

        # Шаг 4: переименование til→ai в имени файла
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

        # Шаг 5: если после переименования файл оказался Tilda-скриптом — удаляем
        if name_lower in delete_service:
            try:
                path.unlink()
                stats.removed += 1
                logger.info(f"🗑 Удалён скрипт: {path.name}")
            except Exception as exc:
                logger.err(f"[assets] Ошибка удаления {path}: {exc}")

    # Создаём прозрачный 1px PNG — используется как замена для логотипов Tilda в HTML
    placeholder = project_root / "images" / "1px.png"
    if not placeholder.exists():
        placeholder.parent.mkdir(parents=True, exist_ok=True)
        placeholder.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc``\x00\x00"
            b"\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        logger.info(f"🧩 Добавлен placeholder: {utils.relpath(placeholder, project_root)}")

    mapping_cfg = service_cfg.rename_map_output
    project_name = logger.get_project_name()
    try:
        mapping_name = mapping_cfg.filename.format(project=project_name)
    except Exception:
        mapping_name = mapping_cfg.filename or f"{project_name}_rename_map.json"

    if mapping_name == "rename_map.json":
        mapping_name = f"{project_name}_rename_map.json"
    if mapping_cfg.location.lower() == "logs":
        mapping_dir = logger.get_logs_dir()
    else:
        mapping_dir = project_root / mapping_cfg.location
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
