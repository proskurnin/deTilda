"""Replace TildaSans/AidaSans with a Google Font equivalent (Manrope).

Tilda Sans хранится на CDN с защитой от скачивания — все попытки fetch
возвращают 404 (см. логи cdn_localizer: ~44 неудачных попытки на woff/woff2/eot).
В результате браузер использует system fallback (Arial), и сайт выглядит не так.

Подход A: подменяем семейство `TildaSans`/`AidaSans` на близкий по дизайну
Google Font — Manrope. Содержит латиницу, кириллицу и латин-расширенный.
Веса 200-800 покрывают почти весь диапазон Tilda Sans (200-900).

Алгоритм:
  1. Файлы с именем fonts-(tilda|aida)sans*.css — это выделенный font-bundle
     Tilda. Заменяем их полное содержимое на @import Google Manrope.
  2. В остальных CSS — удаляем @font-face блоки, ссылающиеся на TildaSans
     или tildacdn URL (стихийно встречающиеся).
  3. Во всех CSS/HTML/JS — заменяем токен 'TildaSans'/'AidaSans' (в кавычках)
     на 'Manrope' внутри font-family деклараций.

Должен запускаться:
  - ДО fonts_localizer (тот скачает Manrope с Google и подставит локальные пути)
  - ДО cdn_localizer (иначе он спамит ~44 предупреждения о неудачных fetch)
"""
from __future__ import annotations

import re
from pathlib import Path

from core import logger, utils

__all__ = ["substitute_tilda_fonts"]


# Целевой Google Font — геометрический sans с кириллицей, ближе всего к Tilda Sans
GOOGLE_FONT_FAMILY = "Manrope"
GOOGLE_FONT_IMPORT = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=Manrope:wght@200;300;400;500;600;700;800&display=swap');\n"
)

# Файл-bundle Tilda для шрифтов: fonts-tildasans.css или fonts-aidasans.css
# (после til→ai в assets.py имя могло измениться)
_DEDICATED_FONT_CSS_RE = re.compile(
    r"^fonts-(?:tilda|aida)sans[^/]*\.css$",
    re.IGNORECASE,
)

# @font-face блок со ссылкой на CDN Tilda ИЛИ объявляющий семейство TildaSans
_FONT_FACE_BLOCK_RE = re.compile(
    r"@font-face\s*\{[^}]*?(?:(?:tilda|aida)cdn|(?:tilda|aida)sans)[^}]*?\}",
    re.IGNORECASE | re.DOTALL,
)

# Токен семейства в кавычках: 'TildaSans', "AidaSans", 'tildaSans', опционально с VF
# Только в кавычках — иначе ловит случайные `aidasans` в URL/именах файлов.
_FONT_FAMILY_TOKEN_RE = re.compile(
    r"""(['"])(?:tilda|aida)sans(?:\s*vf)?\1""",
    re.IGNORECASE,
)


def substitute_tilda_fonts(project_root: Path) -> int:
    """Заменяет ссылки на Tilda Sans на Google Manrope.

    Возвращает количество модифицированных файлов.
    """
    project_root = Path(project_root)
    css_files = list(utils.list_files_recursive(project_root, extensions=(".css",)))
    text_files = list(
        utils.list_files_recursive(
            project_root, extensions=(".css", ".html", ".htm", ".js")
        )
    )

    files_modified = 0
    blocks_removed = 0
    has_dedicated = False

    # Шаг 1: выделенный fonts-*sans*.css → полностью @import Manrope
    for css in css_files:
        if not _DEDICATED_FONT_CSS_RE.match(css.name):
            continue
        utils.safe_write(css, GOOGLE_FONT_IMPORT)
        files_modified += 1
        has_dedicated = True
        logger.info(
            f"🔤 {utils.relpath(css, project_root)} → @import {GOOGLE_FONT_FAMILY}"
        )

    # Шаг 2: стихийные @font-face блоки в остальных CSS — удаляем.
    # Если выделенного файла не было — добавляем @import к первому файлу,
    # из которого что-то удалили (чтобы Manrope всё равно подгрузился).
    for css in css_files:
        if _DEDICATED_FONT_CSS_RE.match(css.name):
            continue
        try:
            text = utils.safe_read(css)
        except Exception as exc:
            logger.warn(f"[font_substitute] Пропуск {css.name}: {exc}")
            continue

        new_text, removed_n = _FONT_FACE_BLOCK_RE.subn("", text)
        if not removed_n:
            continue

        if not has_dedicated and blocks_removed == 0:
            new_text = GOOGLE_FONT_IMPORT + new_text
            has_dedicated = True  # отмечаем, чтобы не добавлять второй раз
        blocks_removed += removed_n
        utils.safe_write(css, new_text)
        files_modified += 1

    # Шаг 3: все текстовые файлы — заменяем токен 'TildaSans'/'AidaSans' → 'Manrope'
    replacement = f"'{GOOGLE_FONT_FAMILY}'"
    for path in text_files:
        try:
            text = utils.safe_read(path)
        except Exception as exc:
            logger.warn(f"[font_substitute] Пропуск {path.name}: {exc}")
            continue

        new_text = _FONT_FAMILY_TOKEN_RE.sub(replacement, text)
        if new_text != text:
            utils.safe_write(path, new_text)
            files_modified += 1

    if files_modified:
        logger.info(
            f"[font_substitute] Tilda Sans → {GOOGLE_FONT_FAMILY}: "
            f"модифицировано {files_modified} файлов, "
            f"удалено @font-face: {blocks_removed}"
        )
    else:
        logger.info("[font_substitute] Ссылок на Tilda Sans не найдено.")

    return files_modified
