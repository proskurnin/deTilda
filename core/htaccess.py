# -*- coding: utf-8 -*-
"""
htaccess.py — анализ маршрутов и базовая обработка правил Apache (.htaccess)
Detilda v4.4 LTS
"""

from pathlib import Path
from core import logger
import re


def parse_htaccess(file_path: Path) -> dict:
    """
    Анализирует файл htaccess и возвращает словарь маршрутов:
    { "/careers": "page24834967.html", "/careers/": "page24834967.html", ... }
    """
    if not file_path.exists():
        logger.warn(f"⚠️ Файл {file_path} не найден для анализа маршрутов.")
        return {}

    htaccess_map = {}
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()

        # Регулярка для извлечения RewriteRule
        rule_pattern = re.compile(r"RewriteRule\s+(\S+)\s+(\S+)", re.IGNORECASE)

        for line in lines:
            if line.strip().startswith("#") or not line.strip():
                continue

            m = rule_pattern.search(line)
            if m:
                pattern, target = m.groups()

                # Приводим пути к удобному виду
                pattern = pattern.strip("^$")
                if not pattern.startswith("/"):
                    pattern = "/" + pattern

                if target.endswith("[NC]"):
                    target = target.replace("[NC]", "").strip()
                if target.endswith("[L]"):
                    target = target.replace("[L]", "").strip()

                htaccess_map[pattern] = target
                logger.info(f"🔗 Правило маршрута: {pattern} → {target}")

    except Exception as e:
        logger.err(f"[htaccess] Ошибка разбора {file_path}: {e}")
        return {}

    if not htaccess_map:
        logger.warn("⚠️ В htaccess не найдено RewriteRule.")
    else:
        logger.ok(f"✅ Анализ htaccess завершён. Найдено {len(htaccess_map)} маршрутов.")

    return htaccess_map