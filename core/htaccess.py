"""Helpers for reading and fixing Apache ``.htaccess`` routing rules.

Шаг 8а конвейера — вспомогательный для refs.py.

Что делает модуль:
  1. Читает .htaccess и извлекает маршруты (RewriteRule, Redirect, DirectoryIndex)
  2. Проверяет существование файлов назначения
  3. Для битых маршрутов применяет одну из стратегий (настраивается в config.yaml):
     - stub_created: копирует 404.html на место отсутствующего файла
     - fallback_redirect: перенаправляет на 404.html
     - removed: удаляет битый маршрут из .htaccess
     - unresolved: оставляет как есть, логирует ошибку

Глобальное состояние:
  _routes_info, _missing_routes, _missing_route_keys — очищаются в начале
  каждого вызова collect_routes(), поэтому безопасны при обработке нескольких архивов.

Результат используется в checker.py (get_route_info, get_missing_routes)
для проверки ссылок и формирования финального отчёта.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from core import logger, utils
from core.config_loader import ConfigLoader

__all__ = [
    "MissingRouteInfo",
    "RouteInfo",
    "collect_routes",
    "get_missing_routes",
    "get_route_info",
]


@dataclass(frozen=True)
class RouteInfo:
    """Информация об одном маршруте из .htaccess."""
    target: str
    exists: bool
    path: Optional[Path] = None


@dataclass(frozen=True)
class MissingRouteInfo:
    """Информация о маршруте с несуществующим назначением."""
    alias: str
    target: str
    action: str          # ok | stub_created | fallback_redirect | removed | unresolved
    replacement: Optional[str] = None


# Глобальный кеш маршрутов — сбрасывается в начале collect_routes()
_routes_info: Dict[str, RouteInfo] = {}
_missing_routes: List[MissingRouteInfo] = []
_missing_route_keys: set[tuple[str, str]] = set()


def _load_patterns(loader: ConfigLoader) -> tuple[re.Pattern[str], re.Pattern[str]]:
    """Компилирует regex для RewriteRule и Redirect из config.yaml."""
    htaccess_cfg = loader.patterns().htaccess_patterns
    rewrite_re = re.compile(
        htaccess_cfg.rewrite_rule
        or r"(?im)^[ \t]*RewriteRule[ \t]+\^/?([a-z0-9\-_/]+)\??\$?[ \t]+([^ \t]+)"
    )
    redirect_re = re.compile(
        htaccess_cfg.redirect
        or r"(?im)^[ \t]*Redirect(?:Permanent|[ \t]+3\d{2})?[ \t]+(/[^ \t]+)[ \t]+([^ \t]+)"
    )
    return rewrite_re, redirect_re


def _iter_htaccess_files(project_root: Path) -> list[Path]:
    """Возвращает список найденных .htaccess файлов в проекте."""
    result: list[Path] = []
    for name in (".htaccess", "htaccess"):
        path = project_root / name
        if path.exists():
            result.append(path)
    return result


def _normalize_alias(alias: str) -> str:
    """Нормализует alias маршрута: убирает лишние слеши, добавляет ведущий /."""
    alias = alias.strip()
    if not alias:
        return "/"
    alias = alias.strip("/")
    return f"/{alias}" if alias else "/"


def _resolve_target_path(target: str, project_root: Path) -> Optional[Path]:
    """Разрешает цель маршрута в абсолютный путь внутри project_root.

    Возвращает None если:
    - цель содержит $1 (динамический маршрут)
    - цель — внешний URL (http://, https://, //)
    - путь выходит за пределы project_root (path traversal)
    """
    target = target.strip()
    if not target:
        return None
    if "$" in target:
        return None
    if any(target.startswith(prefix) for prefix in ("http://", "https://", "//")):
        return None

    clean_target = target.split("?", 1)[0].split("#", 1)[0].strip()
    if not clean_target:
        return None

    raw_path = clean_target.lstrip("/") if clean_target.startswith("/") else clean_target
    try:
        candidate = (project_root / raw_path).resolve()
    except Exception:
        return None

    try:
        project_root_resolved = project_root.resolve()
    except Exception:
        project_root_resolved = project_root
    if candidate != project_root_resolved and project_root_resolved not in candidate.parents:
        return None
    return candidate


def _fix_missing_htaccess_route(
    route: str, target: str, fallback_target: str = "404.html"
) -> str:
    logger.warn(
        f"[htaccess] Маршрут {route} вёл в отсутствующий файл {target}, заменён на {fallback_target}"
    )
    return fallback_target


def _create_route_stub(
    alias: str,
    target: str,
    project_root: Path,
    fallback_target: str,
) -> bool:
    """Создаёт заглушку: копирует fallback_target на место отсутствующего файла маршрута."""
    target_candidate = _resolve_target_path(target, project_root)
    if target_candidate is None:
        logger.warn(
            f"[htaccess] Маршрут {alias}: невозможно создать заглушку для динамической цели {target}"
        )
        return False
    fallback_candidate = _resolve_target_path(fallback_target, project_root)
    if fallback_candidate is None or not fallback_candidate.exists():
        logger.warn(
            f"[htaccess] Маршрут {alias}: не найден шаблон заглушки {fallback_target}"
        )
        return False
    try:
        target_candidate.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fallback_candidate, target_candidate)
        logger.warn(
            f"[htaccess] Маршрут {alias}: создана заглушка {target} из {fallback_target}"
        )
        return True
    except Exception as exc:
        logger.warn(
            f"[htaccess] Маршрут {alias}: не удалось создать заглушку {target}: {exc}"
        )
        return False


def _store_route(
    alias: str,
    target: str,
    project_root: Path,
    routes: Dict[str, str],
    *,
    soft_fallback_enabled: bool = False,
    fallback_target: str = "404.html",
    auto_stub_enabled: bool = False,
    remove_unresolved_enabled: bool = False,
    stats: Any | None = None,
) -> str:
    """Регистрирует маршрут и применяет стратегию если файл назначения отсутствует.

    Порядок проверки стратегий:
      1. Файл существует → маршрут добавляется как есть (action=ok)
      2. auto_stub_enabled → создаём копию fallback_target на месте цели (action=stub_created)
      3. soft_fallback_enabled → перенаправляем на fallback_target (action=fallback_redirect)
      4. remove_unresolved_enabled → удаляем маршрут из .htaccess (action=removed)
      5. Иначе → оставляем как есть, логируем ошибку (action=unresolved)
    """
    alias = _normalize_alias(alias)
    target = target.strip()
    candidate = _resolve_target_path(target, project_root)
    exists = candidate.exists() if candidate else False

    if exists:
        routes[alias] = target
        _routes_info[alias] = RouteInfo(target=target, exists=True, path=candidate)
        logger.debug(f"[htaccess] {alias} → {target} (файл есть)")
        return "ok"

    route_key = (alias, target)
    is_new_missing = route_key not in _missing_route_keys
    if is_new_missing:
        _missing_route_keys.add(route_key)
        logger.err(f"[htaccess] Битый маршрут: {alias} → {target} (файл отсутствует)")

    if auto_stub_enabled and _create_route_stub(alias, target, project_root, fallback_target):
        stub_candidate = _resolve_target_path(target, project_root)
        routes[alias] = target
        _routes_info[alias] = RouteInfo(target=target, exists=True, path=stub_candidate)
        if is_new_missing:
            _increment_stat(stats, "htaccess_routes_initially_broken")
            _increment_stat(stats, "htaccess_routes_autofixed")
            _missing_routes.append(
                MissingRouteInfo(alias=alias, target=target, action="stub_created", replacement=target)
            )
        logger.warn(f"[htaccess] Решение: маршрут {alias} направлен на созданную заглушку {target}")
        return "stub_created"

    if soft_fallback_enabled:
        fallback_candidate = _resolve_target_path(fallback_target, project_root)
        if fallback_candidate and fallback_candidate.exists():
            fixed_target = _fix_missing_htaccess_route(alias, target, fallback_target)
            routes[alias] = fixed_target
            _routes_info[alias] = RouteInfo(target=fixed_target, exists=True, path=fallback_candidate)
            if is_new_missing:
                _increment_stat(stats, "htaccess_routes_initially_broken")
                _increment_stat(stats, "htaccess_routes_autofixed")
                _missing_routes.append(
                    MissingRouteInfo(alias=alias, target=target, action="fallback_redirect", replacement=fixed_target)
                )
            logger.warn(f"[htaccess] Решение: маршрут {alias} перенаправлен на fallback {fixed_target}")
            return "fallback_redirect"

    if remove_unresolved_enabled:
        routes.pop(alias, None)
        _routes_info.pop(alias, None)
        if is_new_missing:
            _increment_stat(stats, "htaccess_routes_initially_broken")
            # Не инкрементируем htaccess_routes_autofixed — удаление ≠ исправление
            _missing_routes.append(
                MissingRouteInfo(alias=alias, target=target, action="removed", replacement=None)
            )
            _increment_stat(stats, "warnings")
        logger.warn(f"[htaccess] Решение: битый маршрут {alias} -> {target} будет удалён из htaccess")
        return "removed"

    # Ни одна стратегия не сработала — оставляем маршрут, но помечаем как нерешённый
    routes[alias] = target
    _routes_info[alias] = RouteInfo(target=target, exists=False, path=candidate if candidate else None)
    if is_new_missing:
        _increment_stat(stats, "htaccess_routes_initially_broken")
        _missing_routes.append(
            MissingRouteInfo(alias=alias, target=target, action="unresolved", replacement=None)
        )
        _increment_stat(stats, "broken_htaccess_routes")
        _increment_stat(stats, "errors")
    logger.err(f"[htaccess] Решение: маршрут {alias} -> {target} не удалось исправить автоматически")
    return "unresolved"


def _increment_stat(stats: Any | None, field: str) -> None:
    """Безопасно увеличивает счётчик в объекте stats если поле существует."""
    if stats is None:
        return
    if not hasattr(stats, field):
        return
    setattr(stats, field, getattr(stats, field, 0) + 1)


def _extract_alias_target(match: re.Match[str]) -> tuple[str, str] | None:
    """Извлекает (alias, target) из regex-матча."""
    groups = match.groups()
    if len(groups) < 2:
        return None
    alias = groups[0]
    target = groups[-1]
    if alias is None or target is None:
        return None
    return alias, target


def collect_routes(
    project_root: Path,
    loader: ConfigLoader,
    stats: Any | None = None,
) -> Dict[str, str]:
    """Основная функция: читает .htaccess, строит таблицу маршрутов, исправляет битые.

    Сбрасывает глобальный кеш перед началом — безопасно при обработке нескольких архивов.
    Возвращает dict {alias: target} для всех валидных маршрутов.
    """
    routes: Dict[str, str] = {}
    _routes_info.clear()
    _missing_routes.clear()
    _missing_route_keys.clear()

    rewrite_re, redirect_re = _load_patterns(loader)
    htaccess_cfg = loader.patterns().htaccess_patterns
    soft_fallback_enabled = htaccess_cfg.soft_fallback_to_404
    auto_stub_enabled = htaccess_cfg.auto_stub_missing_routes
    remove_unresolved_enabled = htaccess_cfg.remove_unresolved_routes
    fallback_target = htaccess_cfg.fallback_target

    for file_path in _iter_htaccess_files(project_root):
        try:
            text = utils.safe_read(file_path)
        except Exception as exc:
            logger.warn(f"[htaccess] Не удалось прочитать {file_path}: {exc}")
            continue

        updated_text = text
        htaccess_changed = False

        def _process_matches(matches: list[re.Match[str]]) -> None:
            nonlocal updated_text, htaccess_changed
            for match in matches:
                extracted = _extract_alias_target(match)
                if extracted is None:
                    logger.warn("[htaccess] Пропущен маршрут: не удалось извлечь alias/target")
                    continue
                alias, target = extracted
                action = _store_route(
                    alias, target, project_root, routes,
                    soft_fallback_enabled=soft_fallback_enabled,
                    fallback_target=fallback_target,
                    auto_stub_enabled=auto_stub_enabled,
                    remove_unresolved_enabled=remove_unresolved_enabled,
                    stats=stats,
                )
                if action == "removed":
                    updated_text = updated_text.replace(match.group(0), "", 1)
                    htaccess_changed = True

        _process_matches(list(rewrite_re.finditer(text)))
        _process_matches(list(redirect_re.finditer(text)))

        # Обрабатываем DirectoryIndex как маршрут к корню "/"
        index_match = re.search(r"DirectoryIndex\s+([^\s]+\.html)", text, re.IGNORECASE)
        if index_match:
            target = index_match.group(1)
            action = _store_route(
                "/", target, project_root, routes,
                soft_fallback_enabled=soft_fallback_enabled,
                fallback_target=fallback_target,
                auto_stub_enabled=auto_stub_enabled,
                remove_unresolved_enabled=remove_unresolved_enabled,
                stats=stats,
            )
            if action == "removed":
                updated_text = updated_text.replace(index_match.group(0), "", 1)
                htaccess_changed = True

        if htaccess_changed and updated_text != text:
            try:
                utils.safe_write(file_path, updated_text)
                logger.warn(
                    f"[htaccess] Битые маршруты удалены из {utils.relpath(file_path, project_root)}"
                )
            except Exception as exc:
                logger.err(
                    f"[htaccess] Не удалось сохранить {utils.relpath(file_path, project_root)}: {exc}"
                )
                _increment_stat(stats, "errors")

    if routes:
        logger.info(f"🔗 Обнаружено маршрутов из htaccess: {len(routes)}")
    else:
        logger.warn("⚠️ В htaccess не найдено маршрутов.")
    return routes


def get_route_info(alias: str) -> Optional[RouteInfo]:
    """Возвращает информацию о маршруте по alias.

    Используется в checker.py при проверке ссылок из HTML.
    """
    return _routes_info.get(_normalize_alias(alias))


def get_missing_routes() -> list[MissingRouteInfo]:
    """Возвращает список битых маршрутов из последнего вызова collect_routes().

    Используется в pipeline.py для финального отчёта.
    """
    return list(_missing_routes)
