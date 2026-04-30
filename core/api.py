"""Public API for the deTilda processing engine.

Стабильная точка входа для программного использования — веб-сервис (v5),
тесты и внешние интеграции должны импортировать отсюда, а не из pipeline.py
напрямую.

Пример:
    from core.api import process_archive
    from core.params import ProcessParams

    stats = process_archive(
        Path("export.zip"),
        params=ProcessParams(email="owner@example.com"),
    )
"""
from __future__ import annotations

from pathlib import Path

from core.params import ProcessParams
from core.pipeline import DetildaPipeline, PipelineStats
from core.version import APP_VERSION

__all__ = ["process_archive"]


def process_archive(
    archive_path: Path | str,
    *,
    params: ProcessParams | None = None,
    dry_run: bool = False,
    logs_dir: Path | str | None = None,
    version: str = APP_VERSION,
) -> PipelineStats:
    """Обрабатывает ZIP-архив Tilda-экспорта и возвращает статистику.

    archive_path: путь к .zip файлу
    params:       параметры запроса (email получателя форм и др.)
    dry_run:      если True — анализ без записи в файлы
    logs_dir:     папка для лог-файлов; по умолчанию repository_root/logs/
    version:      строка версии для заголовков отчётов

    Бросает RuntimeError если архив не удалось распаковать.
    """
    pipeline = DetildaPipeline(
        version=version,
        logs_dir=Path(logs_dir) if logs_dir is not None else None,
        dry_run=dry_run,
        params=params,
    )
    return pipeline.run(Path(archive_path))
