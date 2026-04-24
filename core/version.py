"""Shared deTilda version constants, sourced from manifest.json.

Единственный источник правды для версии — manifest.json.
Все модули, которым нужна версия, импортируют её отсюда.
Менять версию вручную не нужно — используй tools/bump_version.py.
"""
from __future__ import annotations

import json
from pathlib import Path


def _read_manifest() -> dict:
    # Ищем manifest.json на два уровня выше (core/ → корень проекта)
    manifest_path = Path(__file__).resolve().parents[1] / "manifest.json"
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


_manifest = _read_manifest()

# Версия в формате SemVer: "4.7.2"
APP_VERSION: str = _manifest.get("version", "unknown")

# Полное название для вывода в заголовках и логах: "deTilda 4.7.2"
APP_TITLE: str = f"deTilda {APP_VERSION}"

# Поля для финального отчёта
APP_DESCRIPTION: str = _manifest.get("description", "")
APP_LICENSE: str = _manifest.get("license", "")
APP_ENTRY_POINT: str = _manifest.get("entry_point", "main.py")
APP_PYTHON: str = _manifest.get("python", "")
APP_RELEASE_DATE: str = _manifest.get("release_date", "")
