"""Tests for the per-module version registry helpers."""

from __future__ import annotations

import pytest

from core import module_versions
from core.module_versions import (
    get_module_version,
    iter_module_versions,
    module_versions_as_dict,
    register_module_version,
)


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    module_versions._registry.clear()  # type: ignore[attr-defined]
    yield
    module_versions._registry.clear()  # type: ignore[attr-defined]


def test_register_and_fetch_module_version() -> None:
    register_module_version("core.forms", "v4.6 Stable", "Первичная запись")

    info = get_module_version("core.forms")
    assert info is not None
    assert info.module == "core.forms"
    assert info.version == "v4.6 Stable"
    assert info.notes == ("Первичная запись",)


def test_notes_are_normalized_and_serialisable() -> None:
    register_module_version(" core.forms ", " v4.6 Stable ", "", "  milestone ")

    info = get_module_version("core.forms")
    assert info is not None
    assert info.version == "v4.6 Stable"
    assert info.notes == ("milestone",)

    serialised = module_versions_as_dict()
    assert serialised == {
        "core.forms": {"version": "v4.6 Stable", "notes": ["milestone"]}
    }


def test_iter_module_versions_sorted_by_module_name() -> None:
    register_module_version("core.b", "v1")
    register_module_version("core.a", "v2")

    ordered_modules = [info.module for info in iter_module_versions()]
    assert ordered_modules == ["core.a", "core.b"]


def test_register_module_version_requires_names() -> None:
    with pytest.raises(ValueError):
        register_module_version("", "v1")
    with pytest.raises(ValueError):
        register_module_version("core.a", " ")

