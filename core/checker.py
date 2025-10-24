# -*- coding: utf-8 -*-
"""
checker.py — модуль проверки и исправления ссылок Detilda v4.4 LTS
Находит и устраняет битые ссылки в HTML, JS и CSS файлах проекта.
"""

import re
from pathlib import Path
from core import logger
from core.utils import safe_read, safe_write, list_files_recursive


# === Вспомогательные шаблоны ===
LINK_PATTERNS = [
    r'href="([^"]+)"',
    r"href='([^']+)'",
    r'src="([^"]+)"',
    r"src='([^']+)'",
    r'url\(([^)]+)\)',
]

IGNORE_PREFIXES = (
    "#",
    "mailto:",
    "tel:",
    "javascript:",
    "data:",
    "about:",
    "//",
)


# === Исправление ссылок ===
def fix_link(path: Path, link: str, project_root: Path, htaccess_rules: dict) -> str:
    """
    Исправляет битую ссылку на основе htaccess и существующих файлов.
    Возвращает исправленную ссылку или исходную, если не удалось.
    """

    # 1️⃣ Игнорируем внутренние якоря и служебные ссылки
    if any(link.startswith(p) for p in IGNORE_PREFIXES):
        return link

    link = link.strip().strip('"').strip("'")

    # 2️⃣ Проверка на относительный путь
    target = (path.parent / link).resolve()

    if target.exists():
        return link  # файл существует, не трогаем

    # 3️⃣ Применяем правила из htaccess
    for pattern, replacement in htaccess_rules.items():
        if re.search(pattern, link):
            logger.info(f"🔗 Переписано по htaccess: {link} → {replacement}")
            return replacement

    # 4️⃣ Проверяем альтернативные расширения
    html_candidate = target.with_suffix(".html")
    if html_candidate.exists():
        fixed = link.rsplit(".", 1)[0] + ".html"
        logger.info(f"🔗 Исправлено расширение: {link} → {fixed}")
        return fixed

    # 5️⃣ Если не нашли — пробуем подставить index.html
    index_candidate = (project_root / link.strip("/")) / "index.html"
    if index_candidate.exists():
        fixed = str(Path(link) / "index.html").replace("\\", "/")
        logger.info(f"🔗 Добавлен index.html: {link} → {fixed}")
        return fixed

    # 6️⃣ Иначе возвращаем оригинал (битая ссылка)
    return link


# === Основная функция ===
def scan_and_fix_links(project_root: str) -> tuple[int, int, int]:
    """
    Проверяет и исправляет битые ссылки во всех HTML/JS/CSS файлах проекта.
    Возвращает кортеж: (кол-во файлов, исправлено ссылок, оставшихся битых).
    """

    project_root = Path(project_root)
    files = list_files_recursive(project_root, [".html", ".js", ".css"])

    total_checked = 0
    total_fixed = 0
    total_broken = 0

    htaccess_rules = load_htaccess_rules(project_root)
    if not htaccess_rules:
        logger.warn("⚠️ Правила htaccess не найдены или пусты, проверка выполняется в базовом режиме")

    for file_path_str in files:
        path = Path(file_path_str)
        try:
            text = safe_read(path)
        except Exception as e:
            logger.err(f"[checker] Ошибка чтения {path}: {e}")
            continue

        original_text = text
        broken_links_local = 0
        fixed_links_local = 0

        for pattern in LINK_PATTERNS:
            for match in re.findall(pattern, text):
                fixed_link = fix_link(path, match, project_root, htaccess_rules)
                if fixed_link != match:
                    text = text.replace(match, fixed_link)
                    fixed_links_local += 1
                else:
                    # если ссылка битая и не исправлена
                    target = (path.parent / match).resolve()
                    if not target.exists() and not match.startswith("#"):
                        broken_links_local += 1
                        logger.warn(f"💥 Битая ссылка: {match} → {path}")

        # сохраняем, если были исправления
        if text != original_text:
            safe_write(path, text)

        total_checked += 1
        total_fixed += fixed_links_local
        total_broken += broken_links_local

    logger.info(f"🔍 Проверено файлов: {total_checked}")
    logger.info(f"🔗 Исправлено ссылок: {total_fixed}")
    logger.info(f"⚠️ Осталось битых: {total_broken}")

    return total_checked, total_fixed, total_broken


# === Загрузка правил htaccess ===
def load_htaccess_rules(project_root: Path) -> dict:
    """
    Загружает rewrite-правила из файла 'htaccess' (без точки).
    Возвращает словарь паттернов и замен.
    """
    htaccess_path = project_root / "htaccess"
    rules = {}

    if not htaccess_path.exists():
        return rules

    try:
        content = safe_read(htaccess_path)
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("rewriterule"):
                parts = line.split()
                if len(parts) >= 3:
                    pattern = parts[1]
                    replacement = parts[2]
                    rules[pattern] = replacement
        if rules:
            logger.info(f"📜 Загружено {len(rules)} правил из htaccess")
        return rules
    except Exception as e:
        logger.err(f"[checker] Ошибка при чтении htaccess: {e}")
        return {}