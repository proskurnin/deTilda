"""Utilities to normalize the project 404 page.

Шаг 2 конвейера. Tilda кладёт в 404.html свои скрипты, ссылки и заголовок.
Этот модуль приводит страницу к чистому виду:

  1. Заголовок <title> → "Page 404, oooops..."
  2. Ссылки на домены .cc (Tilda) → заменяются на сообщение об ошибке
  3. Сообщение <h1>404</h1> гарантированно присутствует в <body>
  4. Все <script> теги удаляются (inject.py добавит нужные позже)

Вызывается ДО inject.py — поэтому безопасно удалять все скрипты.
"""
from __future__ import annotations

import re
from pathlib import Path

from core import logger, utils

__all__ = ["update_404_page"]


# Находит тег <title>...</title>
_TITLE_PATTERN = re.compile(r"(<title\b[^>]*>)(.*?)(</title>)", re.IGNORECASE | re.DOTALL)

# Находит ссылки на домены .cc (Tilda, aladeco и др.) — заменяем на сообщение об ошибке
_TILDA_LINK_PATTERN = re.compile(
    r"<a\b[^>]*href=[\"']https?://[^\"']*\.cc[\"'][^>]*>.*?</a\s*>",
    re.IGNORECASE | re.DOTALL,
)

# Находит все <script> теги — удаляем, inject.py добавит нужные позже
_SCRIPT_PATTERN = re.compile(
    r"<script\b[^>]*?>[\s\S]*?</script\s*>",
    re.IGNORECASE,
)

_TITLE_TEXT = "Page 404, oooops..."
_MESSAGE_BLOCK = "<h1>404</h1><p>Page not found, oooops...</p>"


def update_404_page(project_root: Path) -> bool:
    """Очищает и нормализует 404.html.

    Возвращает True если файл был изменён, False если изменений не потребовалось
    или файл не найден.
    """
    project_root = Path(project_root)
    page_path = project_root / "404.html"

    if not page_path.exists():
        logger.info("📄 404.html не найден — шаг пропущен.")
        return False

    logger.info("🧾 Обработка страницы 404.html")

    try:
        original = utils.safe_read(page_path)
    except Exception as exc:  # pragma: no cover
        logger.warn(f"[404] Не удалось прочитать 404.html: {exc}")
        return False

    text = original
    changed = False

    # Шаг 1: нормализуем <title>
    def _title_replacer(match: re.Match[str]) -> str:
        nonlocal changed
        if match.group(2).strip() != _TITLE_TEXT:
            changed = True
        return f"{match.group(1)}{_TITLE_TEXT}{match.group(3)}"

    text, title_count = _TITLE_PATTERN.subn(_title_replacer, text)
    if not title_count:
        # Тега <title> нет вообще — вставляем после <head>
        text, inserted = re.subn(
            r"(<head\b[^>]*>)",
            rf"\1<title>{_TITLE_TEXT}</title>",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
        if inserted:
            changed = True

    # Шаг 2: заменяем ссылки на Tilda-домены (.cc) на сообщение об ошибке
    text, anchor_count = _TILDA_LINK_PATTERN.subn(_MESSAGE_BLOCK, text)
    if anchor_count:
        changed = True

    # Шаг 3: гарантируем присутствие сообщения об ошибке в <body>
    if _MESSAGE_BLOCK not in text:
        text, message_inserted = re.subn(
            r"(<body\b[^>]*>)",
            rf"\1{_MESSAGE_BLOCK}",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
        if message_inserted:
            changed = True

    # Шаг 4: удаляем все <script> теги — inject.py добавит нужные позже
    text, script_count = _SCRIPT_PATTERN.subn("", text)
    if script_count:
        changed = True

    if changed and text != original:
        utils.safe_write(page_path, text)
        logger.info("🛠 Обновлена страница 404.html")
        return True

    logger.info("📄 Страница 404.html уже соответствует требованиям.")
    return False
