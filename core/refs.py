# -*- coding: utf-8 -*-
"""
refs.py — маршрутизация, корректировка ссылок и распаковка Detilda v4.5 LTS unified
Теперь собирает статистику исправленных и битых ссылок.
"""

import re
import zipfile
from pathlib import Path
from core import logger, utils

_STATIC_DIRS = ("css/", "js/", "images/", "files/")


# === 🔹 Распаковка архива ===
def unpack_archive(archive_path: Path) -> Path | None:
    """
    Распаковывает ZIP-архив в _workdir с сохранением структуры.
    Возвращает путь к корневой папке проекта.
    """
    workdir = archive_path.parent
    logger.info("📦 Распаковка архива...")

    try:
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            root_folders = list({Path(name).parts[0] for name in zip_ref.namelist()})
            if len(root_folders) == 1:
                root_folder = root_folders[0]
                logger.info(f"Обнаружена единственная корневая папка: '{root_folder}'. Распаковка с сохранением структуры...")
            else:
                root_folder = archive_path.stem
                logger.info(f"Несколько корней — используется '{root_folder}'.")

            zip_ref.extractall(workdir)
            project_root = workdir / root_folder

        logger.info(f"→ Распаковка завершена: {project_root}")
        return project_root

    except Exception as e:
        logger.err(f"💥 Ошибка распаковки архива: {e}")
        return None


# === 🔹 Определение корневой папки ===
def detect_project_root(base_dir: Path) -> Path | None:
    """
    Определяет корневую папку проекта (где лежат страницы HTML или htaccess).
    """
    base_dir = Path(base_dir)
    if not base_dir.exists():
        logger.err(f"⚠️ Каталог не найден: {base_dir}")
        return None

    for p in base_dir.rglob("*"):
        if p.is_file() and (p.name.lower() in ("htaccess", ".htaccess") or p.suffix.lower() == ".html"):
            return p.parent

    logger.warn("⚠️ Не удалось определить корневую папку проекта (нет htaccess или HTML)")
    return base_dir


# === 🔹 Разбор htaccess маршрутов ===
def _parse_htaccess_routes(project_root: Path) -> dict:
    """Читает htaccess и извлекает RewriteRule (alias → файл)."""
    routes = {}
    for name in [".htaccess", "htaccess"]:
        ht = project_root / name
        if ht.exists():
            try:
                text = utils.safe_read(ht)
            except Exception:
                continue

            for m in re.finditer(r"RewriteRule\s+\^([^\$\s]+)\$?\s+([^\s]+\.html)", text, re.I):
                alias, target = m.groups()
                alias = "/" + alias.strip("/")
                routes[alias] = target
                logger.debug(f"[htaccess] {alias} → {target}")

            m = re.search(r"DirectoryIndex\s+([^\s]+\.html)", text, re.I)
            if m:
                routes["/"] = m.group(1).strip()
                logger.debug(f"[htaccess] / → {routes['/']} (DirectoryIndex)")
            break
    return routes


# === 🔹 Исправление абсолютных ссылок с подсчётом ===
def _fix_absolute_links(html_text: str, route_map: dict, rename_map: dict, project_root: Path):
    """Меняет href="/xxx" и src="/xxx" с учётом route_map, rename_map и существования файлов."""
    fixed = 0
    broken = 0

    def repl(m):
        nonlocal fixed, broken
        attr, url = m.group(1), m.group(2)

        # внешние ссылки игнорируем
        if re.match(r"^https?://", url, flags=re.I):
            return m.group(0)
        if not url.startswith("/"):
            return m.group(0)

        # маршруты htaccess
        if url in route_map:
            new = route_map[url]
            if new != url:
                fixed += 1
                return f'{attr}="{new}"'

        # static: убираем ведущий слэш
        for root in _STATIC_DIRS:
            if url.startswith("/" + root):
                new = url[1:]
                if new != url:
                    fixed += 1
                return f'{attr}="{new}"'

        # проверяем rename_map
        url_no_slash = url.lstrip("/")
        if url_no_slash in rename_map:
            new = rename_map[url_no_slash]
            fixed += 1
            return f'{attr}="{new}"'

        # проверяем существование файла
        target = project_root / url_no_slash
        if not target.exists():
            broken += 1

        return m.group(0)

    rx1 = re.compile(r'(href|src)\s*=\s*"(.*?)"', re.I)
    rx2 = re.compile(r"(href|src)\s*=\s*'(.*?)'", re.I)
    html_text = rx1.sub(repl, html_text)
    html_text = rx2.sub(repl, html_text)

    return html_text, fixed, broken


# === 🔹 Корректировка путей в /files ===
def _fix_files_relpaths(file_path: Path, html_text: str) -> str:
    """Корректирует пути в /files/"""
    if "/files/" not in str(file_path.as_posix()):
        return html_text

    def fix_rel(m):
        attr, url = m.group(1), m.group(2)
        if re.match(r"^https?://", url, flags=re.I) or url.startswith("../"):
            return m.group(0)
        for root in _STATIC_DIRS:
            if url.startswith(root):
                new = "../" + url
                return f'{attr}="{new}"'
        return m.group(0)

    rx1 = re.compile(r'(href|src)\s*=\s*"(.*?)"', re.I)
    rx2 = re.compile(r"(href|src)\s*=\s*'(.*?)'", re.I)
    html_text = rx1.sub(fix_rel, html_text)
    html_text = rx2.sub(fix_rel, html_text)
    return html_text


# === 🔹 Основная функция обновления ссылок ===
def update_all_refs_in_project(project_root: str, rename_map: dict, script_dir: str = ".") -> tuple:
    """
    Обновляет все ссылки в HTML/CSS/JS и возвращает статистику:
    (fixed_links, broken_links)
    """
    root = Path(project_root)
    route_map = _parse_htaccess_routes(root)
    logger.info(f"🔗 Обнаружено маршрутов из htaccess: {len(route_map)}")

    fixed_total = 0
    broken_total = 0

    for path in root.rglob("*.html"):
        try:
            s = utils.safe_read(path)
        except Exception as e:
            logger.warn(f"[refs] Пропуск {path}: {e}")
            continue

        orig = s
        s, fixed, broken = _fix_absolute_links(s, route_map, rename_map, root)
        s = _fix_files_relpaths(path, s)
        fixed_total += fixed
        broken_total += broken

        if rename_map:
            for old_rel, new_rel in rename_map.items():
                if old_rel in s:
                    s = s.replace(old_rel, new_rel)
                    fixed_total += 1

        if s != orig:
            utils.safe_write(path, s)
            logger.info(f"🔗 Обновлены ссылки: {path.relative_to(root)}")

    # обновляем CSS/JS
    if rename_map:
        for ext in (".css", ".js"):
            for path in root.rglob(f"*{ext}"):
                try:
                    s = utils.safe_read(path)
                except Exception:
                    continue
                orig = s
                for old_rel, new_rel in rename_map.items():
                    if old_rel in s:
                        s = s.replace(old_rel, new_rel)
                        fixed_total += 1
                if s != orig:
                    utils.safe_write(path, s)
                    logger.info(f"🔗 Обновлены пути в {path.relative_to(root)}")

    logger.info(f"✅ Исправлено ссылок: {fixed_total}, осталось битых: {broken_total}")
    return fixed_total, broken_total