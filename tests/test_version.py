"""Tests for core.version — manifest-driven version metadata."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import version


def test_version_loaded_from_manifest() -> None:
    """APP_VERSION читается из manifest.json — должен быть SemVer."""
    assert version.APP_VERSION
    parts = version.APP_VERSION.split(".")
    assert len(parts) == 3
    for part in parts:
        assert part.isdigit(), f"SemVer часть '{part}' не число"


def test_app_title_includes_version() -> None:
    assert "deTilda" in version.APP_TITLE
    assert version.APP_VERSION in version.APP_TITLE


def test_app_metadata_present() -> None:
    """Метаданные из manifest.json доступны как константы."""
    assert version.APP_LICENSE  # MIT
    assert version.APP_PYTHON  # >=3.10
    assert version.APP_ENTRY_POINT  # main.py
    assert version.APP_RELEASE_DATE  # YYYY-MM-DD
    assert version.APP_DESCRIPTION  # описание приложения


def test_release_date_format() -> None:
    """release_date должен быть в формате YYYY-MM-DD."""
    parts = version.APP_RELEASE_DATE.split("-")
    assert len(parts) == 3
    assert len(parts[0]) == 4  # год
    assert len(parts[1]) == 2  # месяц
    assert len(parts[2]) == 2  # день
