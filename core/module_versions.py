"""Central registry for per-module version annotations.

The application version stored in :mod:`manifest.json` captures global
releases, however it is often handy to understand how individual modules
evolve.  This helper keeps a lightweight in-memory registry that modules can
update from their top-level scope.  During imports modules call
``register_module_version`` with their dotted path, current version and
optional notes describing key milestones.  The collected information can then
be inspected via :func:`get_module_version`, :func:`iter_module_versions` or
converted into serialisable dictionaries for reporting.

Usage example::

    from core.module_versions import register_module_version

    register_module_version(__name__, "v4.6 Stable", "Refined form handling")

Keeping the registration alongside the code change encourages contributors to
update the version when they touch the module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

__all__ = [
    "ModuleVersionInfo",
    "register_module_version",
    "get_module_version",
    "iter_module_versions",
    "module_versions_as_dict",
]


@dataclass(frozen=True, slots=True)
class ModuleVersionInfo:
    """Immutable structure describing a module version entry."""

    module: str
    version: str
    notes: Tuple[str, ...]


_registry: Dict[str, ModuleVersionInfo] = {}


def _validate_non_empty(value: str, field: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"Поле '{field}' не должно быть пустым")
    return value.strip()


def register_module_version(module: str, version: str, *notes: str) -> None:
    """Register the current version for a module.

    Parameters
    ----------
    module:
        Dotted module path (e.g. ``"core.forms"``).  The value is stored as-is
        after trimming whitespace.
    version:
        Human-readable version string describing the state of the module.
    notes:
        Optional milestone descriptions.  Empty or whitespace-only notes are
        ignored.
    """

    module_name = _validate_non_empty(module, "module")
    version_value = _validate_non_empty(version, "version")
    normalized_notes: Tuple[str, ...] = tuple(
        note.strip() for note in notes if note and note.strip()
    )
    _registry[module_name] = ModuleVersionInfo(
        module=module_name, version=version_value, notes=normalized_notes
    )


def get_module_version(module: str) -> ModuleVersionInfo | None:
    """Return the registered version entry for ``module`` if it exists."""

    return _registry.get(module)


def iter_module_versions() -> Iterable[ModuleVersionInfo]:
    """Iterate over all registered module versions in alphabetical order."""

    for module in sorted(_registry):
        yield _registry[module]


def module_versions_as_dict() -> Dict[str, Dict[str, List[str]]]:
    """Return a serialisable representation of the registry."""

    return {
        info.module: {
            "version": info.version,
            "notes": list(info.notes),
        }
        for info in iter_module_versions()
    }

