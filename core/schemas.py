"""Typed Pydantic models for ``config/config.yaml`` sections.

Схемы описывают структуру конфига и служат двум целям:
  1. Валидация при загрузке — невалидные паттерны и структуры выявляются сразу.
  2. Типизированный доступ — вместо dict.get() используются атрибуты объектов.

Иерархия:
  AppConfig
  ├── PatternsConfig        — regex, правила замен, расширения файлов
  ├── ImagesConfig          — обработка изображений и иконок
  ├── ServiceFilesConfig    — скрипты, ресурсы, настройки шагов конвейера
  └── FormsConfig           — настройки send_email.php и smoke-теста

config_loader.py загружает YAML → валидирует через AppConfig → отдаёт
типизированные объекты модулям конвейера.
"""
from __future__ import annotations

import re
from typing import Any, List

from core.pydantic_compat import BaseModel, Field


def _validate_regex(pattern: str, context: str) -> str | None:
    """Проверяет что паттерн компилируется. Возвращает сообщение об ошибке или None."""
    try:
        re.compile(pattern)
        return None
    except re.error as exc:
        return f"{context}: невалидный regex {pattern!r} — {exc}"


def validate_regex_patterns(config: "AppConfig") -> list[str]:
    """Проверяет все regex-поля конфига. Вызывается из config_loader при загрузке.

    Возвращает список сообщений об ошибках (пустой если всё ок).
    Невалидные паттерны логируются как предупреждения — pipeline не останавливается.
    """
    errors: list[str] = []

    for i, link in enumerate(config.patterns.links):
        err = _validate_regex(link, f"patterns.links[{i}]")
        if err:
            errors.append(err)

    for i, rule in enumerate(config.patterns.replace_rules):
        err = _validate_regex(rule.pattern, f"patterns.replace_rules[{i}].pattern")
        if err:
            errors.append(err)

    for i, pattern in enumerate(config.patterns.robots_cleanup_patterns):
        err = _validate_regex(pattern, f"patterns.robots_cleanup_patterns[{i}]")
        if err:
            errors.append(err)

    for i, rule in enumerate(config.patterns.readme_cleanup_patterns):
        err = _validate_regex(rule.pattern, f"patterns.readme_cleanup_patterns[{i}].pattern")
        if err:
            errors.append(err)

    for i, pattern in enumerate(config.patterns.tilda_remnants_patterns):
        err = _validate_regex(pattern, f"patterns.tilda_remnants_patterns[{i}]")
        if err:
            errors.append(err)

    htaccess = config.patterns.htaccess_patterns
    for field_name in ("rewrite_rule", "redirect"):
        pattern = getattr(htaccess, field_name, "")
        if pattern:
            err = _validate_regex(pattern, f"patterns.htaccess_patterns.{field_name}")
            if err:
                errors.append(err)

    return errors


# ---------------------------------------------------------------------------
# Общие типы
# ---------------------------------------------------------------------------

class ReplaceRule(BaseModel):
    """Правило замены: regex-паттерн + строка замены.

    Используется в replace_rules (замена в тексте файлов)
    и readme_cleanup_patterns (очистка readme.txt).
    """
    pattern: str
    replacement: str = ""


# ---------------------------------------------------------------------------
# Секция patterns
# ---------------------------------------------------------------------------

class HtaccessPatterns(BaseModel):
    """Regex и флаги для парсинга .htaccess файла (htaccess.py)."""

    rewrite_rule: str = ""       # regex для RewriteRule директив
    redirect: str = ""           # regex для Redirect директив
    soft_fallback_to_404: bool = False          # редиректить на 404 если файл маршрута не найден
    auto_stub_missing_routes: bool = False      # создавать заглушку для отсутствующего файла
    remove_unresolved_routes: bool = True       # удалять маршруты с несуществующим назначением
    fallback_target: str = "404.html"           # страница-заглушка для битых маршрутов


class PatternsAssets(BaseModel):
    """Паттерн переименования файлов: til→ai в именах (assets.py)."""
    til_to_ai_filename: str = ""


class PatternsConfig(BaseModel):
    """Секция patterns из config.yaml."""

    # Regex для поиска ссылок в HTML/CSS/JS — используются в refs.py и checker.py
    links: List[str] = Field(default_factory=list)

    # Правила замены текста по всему проекту (til→ai, t-→ai-) — refs.py
    replace_rules: List[ReplaceRule] = Field(default_factory=list)

    # Расширения файлов для поиска и замены ссылок
    text_extensions: List[str] = Field(default_factory=list)

    # Ссылки с этими префиксами не проверяются и не трогаются (внешние URL)
    ignore_prefixes: List[str] = Field(default_factory=list)

    # Строки для удаления из robots.txt — cleaners.py
    robots_cleanup_patterns: List[str] = Field(default_factory=list)

    # Правила очистки readme.txt: строки для удаления или замены — cleaners.py
    readme_cleanup_patterns: List[ReplaceRule] = Field(default_factory=list)

    # Настройки парсинга .htaccess — htaccess.py
    htaccess_patterns: HtaccessPatterns = Field(default_factory=HtaccessPatterns)

    # Паттерн переименования файлов — assets.py
    assets: PatternsAssets = Field(default_factory=PatternsAssets)

    # Regex для поиска оставшихся ссылок на домены Tilda — cleaners.py, checker.py
    tilda_remnants_patterns: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Секция images
# ---------------------------------------------------------------------------

class DeletePhysicalFiles(BaseModel):
    """Файлы для физического удаления из проекта (assets.py)."""

    # Удаляются сразу под оригинальным именем — без предварительного переименования
    as_is: List[str] = Field(default_factory=list)


class PatternsList(BaseModel):
    """Простой список строк-паттернов."""
    patterns: List[str] = Field(default_factory=list)


class LinkTagRules(BaseModel):
    """Значения атрибута rel для тегов <link>, которые нужно закомментировать."""
    rel_values: List[str] = Field(default_factory=list)


class ImagesConfig(BaseModel):
    """Секция images из config.yaml — обработка файлов изображений и иконок."""

    # Физически удалить файлы (tildacopy.png, tildafavicon.ico и др.)
    delete_physical_files: DeletePhysicalFiles = Field(default_factory=DeletePhysicalFiles)

    # Ссылки на эти файлы закомментировать в HTML: <!-- src="..." -->
    comment_out_links: PatternsList = Field(default_factory=PatternsList)

    # Теги <link rel="icon"> закомментировать (Tilda ставит свои иконки)
    comment_out_link_tags: LinkTagRules = Field(default_factory=LinkTagRules)

    # Ссылки на логотипы Tilda заменить на прозрачный 1px-пиксель
    replace_links_with_1px: PatternsList = Field(default_factory=PatternsList)


# ---------------------------------------------------------------------------
# Секция service_files
# ---------------------------------------------------------------------------

class RemoteAssetRule(BaseModel):
    """Правило скачивания удалённых ресурсов: папка назначения + расширения файлов."""
    folder: str = ""
    extensions: List[str] = Field(default_factory=list)


class RemoteAssetsConfig(BaseModel):
    """Настройки скачивания ресурсов с CDN Tilda (assets.py)."""
    scan_extensions: List[str] = Field(default_factory=list)  # в каких файлах искать ссылки
    rules: List[RemoteAssetRule] = Field(default_factory=list)  # куда класть скачанные файлы


class FileListConfig(BaseModel):
    """Простой список имён файлов."""
    files: List[str] = Field(default_factory=list)


class ScriptsToDeleteConfig(BaseModel):
    """JS-файлы Tilda для физического удаления из папки проекта (assets.py).

    Удаляет сами файлы. Для удаления тегов <script> в HTML — см. ScriptsToRemoveFromProjectConfig.
    """
    files: List[str] = Field(default_factory=list)


class ScriptsToRemoveFromProjectConfig(BaseModel):
    """Правила удаления тегов <script src="..."> из HTML-файлов (script_cleaner.py).

    filenames: имена файлов (подстрока в атрибуте src)
    patterns: дополнительные regex для инлайн-скриптов без src
    """
    filenames: List[str] = Field(default_factory=list)
    patterns: List[str] = Field(default_factory=list)


class HtmlInjectOptions(BaseModel):
    """Что и куда вставлять в HTML-файлы (inject.py)."""
    inject_handler_script: str = "form-handler.js"  # вставляется перед </body>
    inject_after_marker: str = "</body>"
    inject_head_scripts: List[str] = Field(default_factory=list)  # вставляются перед </head>
    inject_head_marker: str = "</head>"


class NormalizeCaseConfig(BaseModel):
    """Настройки нормализации регистра имён файлов (assets.py)."""
    enabled: bool = True  # включено по умолчанию
    extensions: List[str] = Field(default_factory=list)


class PipelineStagesConfig(BaseModel):
    """Флаги включения отдельных шагов конвейера."""
    normalize_case: NormalizeCaseConfig = Field(default_factory=NormalizeCaseConfig)


class CleanerOptionsConfig(BaseModel):
    """Настройки очистки файлов от ссылок на Tilda (cleaners.py)."""
    files_to_clean_tilda_refs: List[str] = Field(default_factory=list)


class RenameMapOutputConfig(BaseModel):
    """Куда сохранять карту переименований после обработки (assets.py)."""
    filename: str = "{project}_rename_map.json"  # {project} заменяется на имя проекта
    location: str = "logs"


class ResourceCopyItem(BaseModel):
    """Один файл для копирования из resources/ в проект (assets.py)."""
    source: str        # имя файла в resources/
    destination: str   # путь назначения в проекте
    originals: List[str] = Field(default_factory=list)  # старые имена → добавляются в rename_map
    if_missing: bool = False  # копировать только если destination не существует (фолбэк)


class ResourceCopyConfig(BaseModel):
    """Список файлов для копирования из resources/ в проект."""
    files: List[ResourceCopyItem] = Field(default_factory=list)


class ServiceFilesConfig(BaseModel):
    """Секция service_files из config.yaml."""

    remote_assets: RemoteAssetsConfig = Field(default_factory=RemoteAssetsConfig)
    exclude_from_rename: FileListConfig = Field(default_factory=FileListConfig)
    scripts_to_delete: ScriptsToDeleteConfig = Field(default_factory=ScriptsToDeleteConfig)
    scripts_to_remove_from_project: ScriptsToRemoveFromProjectConfig = Field(
        default_factory=ScriptsToRemoveFromProjectConfig
    )
    html_inject_options: HtmlInjectOptions = Field(default_factory=HtmlInjectOptions)
    pipeline_stages: PipelineStagesConfig = Field(default_factory=PipelineStagesConfig)
    cleaner_options: CleanerOptionsConfig = Field(default_factory=CleanerOptionsConfig)
    rename_map_output: RenameMapOutputConfig = Field(default_factory=RenameMapOutputConfig)
    resource_copy: ResourceCopyConfig = Field(default_factory=ResourceCopyConfig)

    @property
    def scripts_to_remove(self) -> List[str]:
        """Быстрый доступ к списку имён скриптов для удаления из HTML."""
        return list(self.scripts_to_remove_from_project.filenames)


# ---------------------------------------------------------------------------
# Секция forms
# ---------------------------------------------------------------------------

class FormsConfig(BaseModel):
    """Секция forms из config.yaml — настройки send_email.php и smoke-теста.

    test_recipients подставляются в const TEST_RECIPIENTS шаблона
    resources/send_email.php при копировании в проект (forms.py).
    """
    test_recipients: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Корневой объект конфига
# ---------------------------------------------------------------------------

class AppConfig(BaseModel):
    """Корневой объект конфига — соответствует структуре config/config.yaml.

    Создаётся через AppConfig.model_validate(yaml_dict) в config_loader.py.
    При ошибке загрузки возвращается AppConfig() с дефолтами — pipeline продолжает работу.
    """
    patterns: PatternsConfig = Field(default_factory=PatternsConfig)
    images: ImagesConfig = Field(default_factory=ImagesConfig)
    service_files: ServiceFilesConfig = Field(default_factory=ServiceFilesConfig)
    forms: FormsConfig = Field(default_factory=FormsConfig)
