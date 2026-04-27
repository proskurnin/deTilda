"""Utilities for removing disallowed Tilda script tags from project files.

Шаг 11 конвейера. Удаляет встроенные скрипты Tilda из HTML-файлов.

Защитный механизм: скрипты удаляются только если наш form-handler.js
и send_email.php уже на месте. Это гарантирует что формы продолжат работать
после удаления оригинальных Tilda-скриптов. Проверка выполняется в pipeline.py
через can_remove_tilda_form_scripts() до вызова remove_disallowed_scripts().

Что удаляется (настраивается в config.yaml):
  - <script src="tilda-stat-1.0.min.js"> — аналитика Tilda
  - <script src="tilda-forms-1.0.min.js"> — обработчик форм Tilda
  - <script src="tilda-fallback-1.0.min.js"> — fallback для форм
  - <script src="tilda-events-1.0.min.js"> — события Tilda
  - Аналоги с префиксом aida-* (старое название)
  - Скрипты перед комментарием <!-- Stat --> (маркер статистики Tilda)

runtime_scripts.py может защитить некоторые скрипты от удаления,
если в проекте есть видео, галереи или lazyload-зависимости.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from core import logger, utils
from core.config_loader import ConfigLoader
from core.runtime_scripts import filter_removable_scripts

__all__ = ["can_remove_tilda_form_scripts", "remove_disallowed_scripts"]


def can_remove_tilda_form_scripts(project_root: Path) -> bool:
    """Проверяет что наши обработчики форм уже на месте.

    Удалять Tilda-скрипты форм безопасно только если:
    - send_email.php скопирован из resources/
    - js/form-handler.js скопирован из resources/js/

    Оба файла создаются на шаге 4 (forms.py).
    """
    project_root = Path(project_root)
    send_email_php = project_root / "send_email.php"
    form_handler_js = project_root / "js" / "form-handler.js"
    return send_email_php.exists() and form_handler_js.exists()


def _collect_script_rules(loader: ConfigLoader) -> tuple[list[str], list[re.Pattern[str]]]:
    """Читает список скриптов для удаления из config.yaml.

    Возвращает (имена файлов, скомпилированные regex-паттерны).
    Имена — подстрока в атрибуте src. Паттерны — для инлайн-скриптов без src.
    """
    removal_cfg = loader.service_files().scripts_to_remove_from_project
    names: list[str] = [v.strip() for v in removal_cfg.filenames if v.strip()]
    patterns: list[re.Pattern[str]] = []

    for raw_pattern in removal_cfg.patterns:
        if not raw_pattern.strip():
            continue
        try:
            patterns.append(re.compile(raw_pattern.strip(), re.IGNORECASE))
        except re.error as exc:
            logger.warn(
                "[script_cleaner] Некорректный паттерн в конфиге scripts_to_remove_from_project: "
                f"{raw_pattern!r} ({exc})"
            )

    # Дедупликация с сохранением порядка
    return list(dict.fromkeys(names)), patterns


# Паттерны для парсинга <script>...</script> блоков
_SCRIPT_OPEN_RE = re.compile(r"<script\b", re.IGNORECASE)
_SCRIPT_CLOSE_RE = re.compile(r"</script\s*>", re.IGNORECASE)
_SRC_ATTR_RE = re.compile(
    r"\bsrc\s*=\s*(?:" +
    r'"([^"\\>]*)"' +
    r"|'([^'\\>]*)'" +
    r"|([^>\s]+))",
    re.IGNORECASE,
)

# Tilda маркирует скрипты статистики комментарием <!-- Stat --> перед тегом.
# Если находим такой комментарий перед <script> — удаляем вместе с ним.
_STAT_COMMENT_TAIL_RE = re.compile(r"(\s*<!--\s*Stat\s*-->\s*)$", re.IGNORECASE)


def _normalize_src(value: str) -> str:
    """Нормализует значение src: убирает query/fragment, оставляет только имя файла в нижнем регистре."""
    value = value.strip()
    if not value:
        return ""
    normalized = value.split("#", 1)[0].split("?", 1)[0]
    normalized = normalized.replace("\\", "/")
    return normalized.rsplit("/", 1)[-1].lower()


def _iter_script_blocks(text: str) -> Iterator[tuple[int, int, str, str]]:
    """Итерируется по блокам <script>...</script> в тексте.

    Yields: (start, end, full_block, opening_tag)
    """
    pos = 0
    while True:
        match = _SCRIPT_OPEN_RE.search(text, pos)
        if not match:
            break

        start = match.start()
        tag_start = match.end()
        tag_close_index = text.find(">", tag_start)
        if tag_close_index == -1:
            break

        tag_close = tag_close_index + 1
        start_tag = text[start:tag_close]

        # Самозакрывающийся тег (<script ... />) — нет тела
        if start_tag.rstrip().endswith("/>"):
            yield start, tag_close, start_tag, start_tag
            pos = tag_close
            continue

        end_match = _SCRIPT_CLOSE_RE.search(text, tag_close)
        if not end_match:
            pos = tag_close
            continue

        end = end_match.end()
        block = text[start:end]
        yield start, end, block, start_tag
        pos = end


def _filter_disallowed_scripts(script_names: list[str], project_root: Path) -> list[str]:
    """Фильтрует список: исключает скрипты нужные для видео/галерей/lazyload.

    filter_removable_scripts из runtime_scripts.py анализирует HTML проекта
    и возвращает только те скрипты, которые безопасно удалить.
    """
    if not script_names:
        return []
    filtered, preserved = filter_removable_scripts(script_names, project_root)
    if preserved:
        logger.info(
            "[script_cleaner] Обнаружены видео/галереи/lazyload-маркеры — сохраняем runtime-скрипты: "
            + ", ".join(sorted(set(preserved)))
        )
    return filtered


def remove_disallowed_scripts(project_root: Path, loader: ConfigLoader) -> int:
    """Удаляет теги <script src="..."> Tilda из всех текстовых файлов проекта.

    Алгоритм для каждого файла:
      1. Итерируемся по всем <script>...</script> блокам
      2. Нормализуем src → имя файла в нижнем регистре
      3. Если имя в списке запрещённых — удаляем блок
      4. Если перед блоком есть <!-- Stat --> — удаляем вместе с ним

    Возвращает общее количество удалённых тегов.
    """
    project_root = Path(project_root)
    script_names, extra_patterns = _collect_script_rules(loader)
    script_names = _filter_disallowed_scripts(script_names, project_root)
    if not script_names and not extra_patterns:
        logger.info("[script_cleaner] Список скриптов для удаления пуст — пропуск шага.")
        return 0

    text_extensions = tuple(loader.patterns().text_extensions) or (
        ".html", ".htm", ".php", ".js", ".css", ".txt",
    )

    logger.info(f"[script_cleaner] Используем конфиг: {loader.config_path}")
    logger.info("[script_cleaner] Расширения для проверки: " + ", ".join(text_extensions))
    logger.info(
        "[script_cleaner] Скрипты для удаления: "
        + (", ".join(script_names) if script_names else "—")
    )
    if extra_patterns:
        logger.info(f"[script_cleaner] Доп. паттерны: {len(extra_patterns)}")

    removed_tags = 0
    updated_files = 0
    lowered_names = [name.lower() for name in script_names]
    names_lookup = set(lowered_names)

    for path in utils.list_files_recursive(project_root, extensions=text_extensions):
        try:
            text = utils.safe_read(path)
        except Exception as exc:
            logger.warn(f"[script_cleaner] Пропуск {path.name}: {exc}")
            continue

        original = text
        removed_in_file = 0
        pieces: list[str] = []
        last_index = 0

        for start, end, block, start_tag in _iter_script_blocks(original):
            remove_block = False

            # Проверяем комментарий <!-- Stat --> перед тегом
            prefix = original[last_index:start]
            match_comment = _STAT_COMMENT_TAIL_RE.search(prefix) if prefix else None

            # Извлекаем и нормализуем атрибут src
            match = _SRC_ATTR_RE.search(start_tag)
            normalized_src = ""
            if match:
                src_value = next((group for group in match.groups() if group), "")
                normalized_src = _normalize_src(src_value)

            if normalized_src and normalized_src in names_lookup:
                remove_block = True
            elif extra_patterns and any(pattern.search(block) for pattern in extra_patterns):
                remove_block = True
            elif match_comment:
                remove_block = True
            else:
                # Проверка имени файла внутри ТЕЛА скрипта (не только src):
                # для inline-скриптов которые динамически загружают удалённые
                # файлы через setTimeout/createElement (например aida-stat).
                lowered_block = block.lower()
                for name in lowered_names:
                    # Имя должно быть окружено кавычками или слешем — не часть
                    # большего идентификатора. Это уменьшает риск false-positive.
                    if (f'"{name}"' in lowered_block
                            or f"'{name}'" in lowered_block
                            or f"/{name}" in lowered_block):
                        remove_block = True
                        break

            if remove_block:
                if match_comment:
                    prefix = prefix[: match_comment.start()]
                pieces.append(prefix)
                last_index = end
                removed_in_file += 1

        if removed_in_file:
            pieces.append(original[last_index:])
            text = "".join(pieces)
        elif script_names:
            # Скрипт упоминается в файле, но src не совпал точно — логируем для диагностики
            lowered_text = original.lower()
            matched_names = [
                name for name, lowered in zip(script_names, lowered_names) if lowered in lowered_text
            ]
            if matched_names:
                logger.debug(
                    "[script_cleaner] Найдены упоминания скриптов, но src не совпадает: "
                    f"{matched_names} в {utils.relpath(path, project_root)}"
                )

        if removed_in_file and text != original:
            utils.safe_write(path, text)
            removed_tags += removed_in_file
            updated_files += 1
            logger.info(
                f"🗑 Удалены теги скриптов ({removed_in_file}) в {utils.relpath(path, project_root)}"
            )

    if removed_tags:
        logger.info(f"🧹 Скрипты удалены: всего {removed_tags} тегов в {updated_files} файлах.")
    else:
        logger.info("🧹 Скрипты для удаления не найдены.")

    return removed_tags
