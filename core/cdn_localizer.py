"""Localize remaining Tilda CDN references to local files.

После шагов assets и refs в коде могут остаться ссылки на CDN Tilda:
  - прямые URL: https://static.tildacdn.com/lib/flags/flags7.png
  - после til→ai: https://static.aidacdn.com/lib/flags/flags7.png (несуществующий домен!)
  - конкатенации в JS: 'https://static.aidacdn.' + zone() + '/lib/flags/flags7.png'

Эти URL — статичные ресурсы (спрайты иконок, флаги, библиотеки и т.д.).
Lib пути особенно важны: например `lib/flags/flags7.png` — спрайт флагов
для phone-input. Без него флаги в форме выбора страны не отображаются.

Что делает модуль:
1. Сканирует HTML/CSS/JS файлы проекта
2. Находит прямые URL и JS-конкатенации с tildacdn/aidacdn доменами
3. Скачивает каждый файл с реального static.tildacdn.com
4. Сохраняет в проекте с сохранением структуры путей (lib/flags/flags7.png)
5. Заменяет URL на относительный путь
"""
from __future__ import annotations

import re
import urllib.error
from urllib.parse import urlsplit
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from core import logger, utils
from core.downloader import fetch_bytes

__all__ = [
    "CdnLocalizationResult",
    "cleanup_unresolved_cdn_references",
    "download_cdn_url",
    "is_static_tilda_cdn_url",
    "localize_cdn_urls",
]


@dataclass
class CdnLocalizationResult:
    files_updated: int = 0
    urls_localized: int = 0
    download_failures: int = 0
    failed_urls: list[str] = field(default_factory=list)


# Реальный домен Tilda для скачивания. Используем .com — самая стабильная зона.
_REAL_CDN_HOST = "static.tildacdn.com"

# Расширения файлов, в которых ищем CDN-ссылки
_TARGET_EXTENSIONS = (".html", ".htm", ".css", ".js")

# Прямой URL: https://static.tildacdn.com/path/file.ext или aidacdn (после til→ai)
_DIRECT_URL_RE = re.compile(
    r"(?:https?:)?//static\.(?:tilda|aida)cdn\.[a-z]+/[^\s'\"\\)]+",
    re.IGNORECASE,
)

# Конкатенация в JS:
#   "...prefix...https://static.aidacdn." + funcCall() + "/path/file.ext"...suffix...
#
# Структура: открывающая `"` далеко слева → текст до URL → закрывающая `"` (q1)
# → JS-конкатенация `+ var() +` → открывающая `'` (q2) → path → закрывающая `'`.
#
# Пример: 'background-image:url(https://static.tildacdn." + zone() + "/lib/flags/flags7.png);...}'
#
# КРИТИЧНО: q1 и q2 могут быть РАЗНЫХ типов (`"..."` и `'...'`).
# Внутри второй строки могут быть кавычки другого типа (например `flag="np"`),
# поэтому для второй части используем backreference (?P=q2) — match идёт ДО
# именно той же кавычки что открывала, а не до первой попавшейся.
#
# Замена должна сохранить q1 + concat + q2 чтобы баланс кавычек в файле не сломался.
_CONCAT_URL_RE = re.compile(
    r"""
    https?://static\.(?:tilda|aida)cdn\.
    (?P<q1>['"])                        # закрывающая кавычка первой части
    (?P<concat>\s*\+\s*[^+]+?\+\s*)     # + variable() +
    (?P<q2>['"])                        # открывающая кавычка второй части
    (?P<rest>(?:(?!(?P=q2)).)+)         # path + suffix — всё кроме q2
    (?P=q2)                             # закрывающая кавычка второй части
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Из строки "/lib/flags/flags7.png)" извлекает path и suffix отдельно
_PATH_AND_SUFFIX_RE = re.compile(r"(/[a-zA-Z0-9_/.\-]+)(.*)")

# Обратное преобразование til→ai: \baida → tilda, чтобы скачать с реального tildacdn.com.
# Применяется ТОЛЬКО при формировании URL для скачивания, файл сохраняется по
# оригинальному path (с aida — каким он стоит в JS после refs.py).
#
# Замечание: оригинальное правило `\btil` → `ai` "съедает" букву `l`,
# поэтому простое \baid → til даёт `tilasans` вместо `tildasans`.
# Регекс \baida → tilda восстанавливает потерянную букву корректно:
#   aidacdn  → tildacdn
#   aidasans → tildasans
_REVERSE_TIL_AI_RE = re.compile(r"\baida", re.IGNORECASE)


def _reverse_path_for_real_cdn(path: str) -> str:
    """Возвращает путь в оригинальной форме Tilda для запроса на реальный CDN."""
    return _REVERSE_TIL_AI_RE.sub("tilda", path)


def _extract_path_from_url(url: str) -> str | None:
    """Из https://static.tildacdn.com/lib/flags/flags7.png → lib/flags/flags7.png"""
    normalized_url = f"https:{url}" if url.startswith("//") else url
    split = urlsplit(normalized_url)
    if not split.netloc.lower().startswith("static.") or not re.search(
        r"\.(?:tilda|aida)cdn\.", split.netloc, re.IGNORECASE
    ):
        return None
    return split.path.lstrip("/")


def is_static_tilda_cdn_url(url: str) -> bool:
    """Return True for static Tilda CDN URLs we know how to localize."""
    return _extract_path_from_url(url) is not None


def _candidate_urls_for_path(path: str) -> list[str]:
    candidates = [path]
    reversed_path = _reverse_path_for_real_cdn(path)
    if reversed_path != path:
        candidates.append(reversed_path)
    return [f"https://{_REAL_CDN_HOST}/{candidate}" for candidate in candidates]


def download_cdn_url(
    url: str,
    project_root: Path,
    cache: dict[str, object] | None = None,
) -> Path | None:
    """Download a static Tilda CDN URL into project_root preserving CDN path."""
    path = _extract_path_from_url(url)
    if not path:
        return None
    return _download_to_local(path, Path(project_root), cache if cache is not None else {})


# Sentinel для negative cache (path известен как недоступный — не пробуем снова)
_DOWNLOAD_FAILED = object()


def _download_to_local(
    path: str,
    project_root: Path,
    cache: dict[str, object],
) -> Path | None:
    """Скачивает path с реального tildacdn.com в project_root/path с сохранением структуры.

    Сначала пробует path как есть (URL мог не пострадать от til→ai).
    Если 404 — применяет обратное преобразование aida→tilda и пробует снова
    (URL был переименован refs.py, но файл на CDN под оригинальным именем).

    Negative cache: если путь не скачался — больше не пробуем (кеш _DOWNLOAD_FAILED).
    Это критично — без него один и тот же битый URL будет пытаться скачаться
    на каждой из десятков HTML/CSS страниц проекта (минуты лишнего ожидания).

    Файл сохраняется по path как он стоит в JS — JS будет его искать именно так.
    """
    cached = cache.get(path)
    if cached is _DOWNLOAD_FAILED:
        return None
    if isinstance(cached, Path):
        return cached

    # КРИТИЧНО: если файл уже существует локально — НЕ скачивать.
    # Иначе мы перезапишем версию обработанную refs.py (где til→ai в строках)
    # свежей оригинальной с CDN — и идентификаторы CSS-классов в JS снова
    # станут .t-* вместо .ai-*, ломая querySelector в браузере.
    destination = project_root / path
    if destination.exists() and destination.stat().st_size > 0:
        cache[path] = destination
        return destination

    data: bytes | None = None
    for real_url in _candidate_urls_for_path(path):
        try:
            # Короткий timeout — для невалидных URL не ждём 20 секунд
            data, _ = fetch_bytes(real_url, timeout=8, user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ))
            break
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            logger.warn(f"[cdn] Не удалось скачать {real_url}: {exc}")
            continue
        except Exception as exc:  # pragma: no cover
            logger.warn(f"[cdn] Неожиданная ошибка скачивания {real_url}: {exc}")
            continue

    if data is None:
        # Запоминаем что путь недоступен — не пробуем повторно
        cache[path] = _DOWNLOAD_FAILED
        return None

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.write_bytes(data)
    except Exception as exc:
        logger.err(f"[cdn] Ошибка записи {destination}: {exc}")
        return None

    logger.info(f"🌐 Локализован CDN ресурс: → {path}")
    cache[path] = destination
    return destination


def localize_cdn_urls(project_root: Path) -> CdnLocalizationResult:
    """Главная функция: сканирует HTML/CSS/JS и локализует CDN-ссылки.

    Применяется после refs.py — то есть в коде уже могут быть ссылки
    с обоими доменами (tildacdn до til→ai, aidacdn после).
    """
    project_root = Path(project_root)
    result = CdnLocalizationResult()
    download_cache: dict[str, object] = {}
    failed_paths: set[str] = set()

    def _record_download_failure(path: str) -> None:
        if path in failed_paths:
            return
        failed_paths.add(path)
        result.download_failures += 1
        result.failed_urls.extend(_candidate_urls_for_path(path))

    for file_path in utils.list_files_recursive(project_root, extensions=_TARGET_EXTENSIONS):
        try:
            text = utils.safe_read(file_path)
        except Exception:
            continue

        original = text

        # 1. Обрабатываем JS-конкатенации первыми (они длиннее, чтобы не схлопнуться в прямой URL)
        def _replace_concat(match: re.Match[str]) -> str:
            rest = match.group("rest")
            q1 = match.group("q1")  # закрывающая кавычка первой строки
            q2 = match.group("q2")  # кавычка второй строки (открывающая = закрывающая)

            # rest = "/lib/flags/flags7.png)" → path="lib/flags/flags7.png", suffix=")"
            path_match = _PATH_AND_SUFFIX_RE.match(rest)
            if not path_match:
                return match.group(0)

            path = path_match.group(1).lstrip("/")
            suffix = path_match.group(2)

            local = _download_to_local(path, project_root, download_cache)
            if local is None:
                _record_download_failure(path)
                return match.group(0)

            result.urls_localized += 1
            # Заменяем `https://...cdn.q1 +var()+ q2 rest q2` на `q1+q2 path suffix q2`.
            # Это:
            #  • Закрывает первую строку (q1) — иначе её открывающая кавычка
            #    далеко слева останется без пары и сломает синтаксис.
            #  • Конкатенирует через `+` — заменяет вызов функции (var() == TLD)
            #    нашим локальным path. Функция больше не нужна — путь относительный.
            #  • Открывает новую строку (q2) с path и закрывает (q2). Тип q2
            #    выбран чтобы не конфликтовать с возможными q1-кавычками внутри
            #    rest (например `flag="np"` внутри `'...'`-строки).
            return f"{q1}+{q2}{path}{suffix}{q2}"

        text = _CONCAT_URL_RE.sub(_replace_concat, text)

        # 2. Прямые URL
        def _replace_direct(match: re.Match[str]) -> str:
            url = match.group(0)
            path = _extract_path_from_url(url)
            if not path:
                return url
            local = _download_to_local(path, project_root, download_cache)
            if local is None:
                _record_download_failure(path)
                return url
            result.urls_localized += 1
            return path

        text = _DIRECT_URL_RE.sub(_replace_direct, text)

        if text != original:
            utils.safe_write(file_path, text)
            result.files_updated += 1

    if result.urls_localized:
        logger.info(
            f"[cdn] Локализовано CDN-ссылок: {result.urls_localized} "
            f"в {result.files_updated} файлах"
        )
    if result.download_failures:
        logger.warn(
            f"[cdn] Не удалось скачать: {result.download_failures} уникальных ресурсов"
        )
        for failed_url in result.failed_urls[:10]:
            logger.warn(f"[cdn] Unresolved URL: {failed_url}")
        if len(result.failed_urls) > 10:
            logger.warn(f"[cdn] И ещё {len(result.failed_urls) - 10} URL")

    return result


# Регексы для удаления нерешённых CDN-ссылок ===

# @font-face блок целиком, если внутри есть tildacdn или aidacdn
_FONT_FACE_BLOCK_RE = re.compile(
    r"@font-face\s*\{[^}]*?(?:tilda|aida)cdn[^}]*?\}",
    re.IGNORECASE | re.DOTALL,
)

# <script src="...(tilda|aida)cdn..."></script>
_SCRIPT_TAG_RE = re.compile(
    r"<script\b[^>]*src=['\"][^'\"]*(?:tilda|aida)cdn[^'\"]*['\"][^>]*>"
    r"\s*</script\s*>",
    re.IGNORECASE,
)

# <link rel="..." href="...(tilda|aida)cdn..." ...>
# Не трогаем dns-prefetch и preconnect — это безопасные хинты, не блокируют
_LINK_TAG_RE = re.compile(
    r"<link\b[^>]*href=['\"][^'\"]*(?:tilda|aida)cdn[^'\"]*['\"][^>]*/?>",
    re.IGNORECASE,
)


@dataclass
class CleanupResult:
    files_updated: int = 0
    font_faces_removed: int = 0
    scripts_removed: int = 0
    links_removed: int = 0


def cleanup_unresolved_cdn_references(project_root: Path) -> CleanupResult:
    """Удаляет ссылки на несуществующие CDN-ресурсы.

    Вызывается ПОСЛЕ localize_cdn_urls. К этому моменту все URL которые удалось
    скачать — уже заменены на относительные пути. То что осталось — недоступно
    с CDN (защищённые шрифты Tilda Sans и т.п.).

    Эти ссылки нужно убрать из HTML/CSS, иначе браузер пытается загрузить их,
    ждёт 30+ секунд timeout на каждый, и страница загружается с большим лагом.

    Удаляются:
      - @font-face блоки целиком (браузер использует system fallback)
      - <script src="...cdn..."> теги (если такой скрипт критичен — мы бы его скачали)
      - <link href="...cdn..."> теги КРОМЕ dns-prefetch и preconnect (хинты безопасны)
    """
    project_root = Path(project_root)
    result = CleanupResult()

    for file_path in utils.list_files_recursive(project_root, extensions=_TARGET_EXTENSIONS):
        try:
            text = utils.safe_read(file_path)
        except Exception:
            continue

        original = text

        # Считаем удалённые блоки
        text, font_count = _FONT_FACE_BLOCK_RE.subn("", text)
        text, script_count = _SCRIPT_TAG_RE.subn("", text)

        # Для <link> исключаем безопасные хинты
        def _link_replacer(match: re.Match[str]) -> str:
            tag = match.group(0)
            # dns-prefetch и preconnect не блокируют рендеринг, оставляем
            if re.search(r"rel=['\"]?(?:dns-prefetch|preconnect)['\"]?", tag, re.IGNORECASE):
                return tag
            return ""

        text, link_subs = _LINK_TAG_RE.subn(_link_replacer, text)
        link_count = sum(1 for _ in _LINK_TAG_RE.finditer(original)) - sum(
            1 for _ in _LINK_TAG_RE.finditer(text)
        )

        if text != original:
            utils.safe_write(file_path, text)
            result.files_updated += 1
            result.font_faces_removed += font_count
            result.scripts_removed += script_count
            result.links_removed += link_count

    if result.files_updated:
        logger.info(
            f"[cdn-cleanup] Удалено нерешённых CDN-ссылок: "
            f"@font-face={result.font_faces_removed}, "
            f"<script>={result.scripts_removed}, "
            f"<link>={result.links_removed} "
            f"в {result.files_updated} файлах"
        )

    return result
