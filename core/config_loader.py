"""Typed access helpers for :mod:`config/config.yaml`.

Единственная точка загрузки конфига в приложении.
Модули конвейера получают типизированные объекты через ConfigLoader:

    loader = ConfigLoader(repository_root)
    links = loader.patterns().links          # List[str]
    opts  = loader.service_files().html_inject_options  # HtmlInjectOptions

Жизненный цикл:
  - ConfigLoader создаётся в ProjectContext.from_project_root()
  - Конфиг загружается лениво при первом обращении и кэшируется
  - При ошибке загрузки возвращается AppConfig() с дефолтами
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml
from core.pydantic_compat import ValidationError

from core import logger
from core.schemas import (
    AppConfig,
    FontSubstituteConfig,
    FormsConfig,
    ImagesConfig,
    PatternsConfig,
    ServiceFilesConfig,
    WebConfig,
    validate_regex_patterns,
)

_DEFAULT_BASE_DIR = Path(__file__).resolve().parent.parent


def _normalize_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Нормализует сырой YAML перед передачей в Pydantic.

    readme_cleanup_patterns в config.yaml содержит смешанные типы:
      - строки: "(?im)^.*Published on Tilda\\.cc.*\\n?"
      - словари: {pattern: "...", replacement: "..."}

    Pydantic ожидает только словари для маппинга в ReplaceRule.
    Эта функция конвертирует строки в словари до валидации.
    """
    patterns = data.get("patterns")
    if not isinstance(patterns, dict):
        return data

    raw = patterns.get("readme_cleanup_patterns", [])
    if not isinstance(raw, list):
        return data

    normalized = []
    for item in raw:
        if isinstance(item, str):
            normalized.append({"pattern": item, "replacement": ""})
        elif isinstance(item, dict):
            normalized.append(item)
        else:
            normalized.append(item)

    patterns["readme_cleanup_patterns"] = normalized
    return data


def _validate_config(data: Dict[str, Any]) -> AppConfig:
    """Валидирует словарь через Pydantic-схему AppConfig."""
    data = _normalize_data(data)
    if hasattr(AppConfig, "model_validate"):
        return AppConfig.model_validate(data)  # type: ignore[attr-defined]
    return AppConfig.parse_obj(data)


class ConfigLoader:
    """Загружает и кэширует ``config/config.yaml``.

    Принимает base_dir — корень репозитория (где лежит папка config/).
    В рантайме создаётся в ProjectContext, передаётся во все модули конвейера.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or _DEFAULT_BASE_DIR
        self._cache: AppConfig | None = None  # загружается лениво

    @property
    def base_dir(self) -> Path:
        """Корень репозитория — нужен assets.py для поиска resources/."""
        return Path(self._base_dir)

    @property
    def config_path(self) -> Path:
        return Path(self._base_dir) / "config" / "config.yaml"

    def _load(self) -> AppConfig:
        """Загружает конфиг при первом обращении, кэширует результат."""
        if self._cache is not None:
            return self._cache

        path = self.config_path
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                raise ValueError("config.yaml должен содержать словарь")
            config = _validate_config(data)
            # Проверяем все regex-паттерны сразу — невалидные логируются как warnings
            for error in validate_regex_patterns(config):
                logger.warn(f"[config_loader] {error}")
        except FileNotFoundError:
            logger.err(f"[config_loader] Не найден файл конфигурации: {path}")
            config = AppConfig()
        except ValidationError as exc:
            logger.err(f"[config_loader] Ошибка валидации {path}: {exc}")
            config = AppConfig()
        except Exception as exc:
            logger.err(f"[config_loader] Ошибка чтения {path}: {exc}")
            config = AppConfig()

        self._cache = config
        return config

    @property
    def config(self) -> AppConfig:
        """Полный типизированный конфиг (используется в project.py)."""
        return self._load()

    def patterns(self) -> PatternsConfig:
        """Секция patterns — ссылки, замены, расширения файлов."""
        return self._load().patterns

    def images(self) -> ImagesConfig:
        """Секция images — правила обработки изображений."""
        return self._load().images

    def service_files(self) -> ServiceFilesConfig:
        """Секция service_files — скрипты, ресурсы, настройки шагов."""
        return self._load().service_files

    def forms(self) -> FormsConfig:
        """Секция forms — настройки send_email.php и smoke-теста форм."""
        return self._load().forms

    def font_substitute(self) -> FontSubstituteConfig:
        """Секция font_substitute — замена Tilda Sans на Google Font."""
        return self._load().font_substitute

    def web(self) -> WebConfig:
        """Секция web — параметры веб-сервиса."""
        return self._load().web
