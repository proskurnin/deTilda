"""Helpers for synchronising ``manifest.json`` with build artefacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def _load_manifest(manifest_path: Path) -> Dict[str, Any]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):  # pragma: no cover - defensive branch
        raise ValueError("manifest.json должен содержать объект JSON")
    return data


def _dump_manifest(manifest_path: Path, data: Dict[str, Any]) -> None:
    manifest_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _guess_version_from_package(package_name: str) -> str | None:
    name = Path(package_name).name
    if not name:
        return None

    if name.lower().endswith(".zip"):
        name = name[:-4]

    prefix = "detilda_"
    if name.lower().startswith(prefix):
        name = name[len(prefix) :]

    normalized = " ".join(name.replace("_", " ").split())
    return normalized or None


def synchronize_manifest_with_build(
    package_path: Path,
    version: str | None = None,
    manifest_path: Path | None = None,
) -> Dict[str, Any]:
    """Update ``manifest.json`` using the supplied build artefact.

    Parameters
    ----------
    package_path:
        Path to the produced build archive.
    version:
        Optional explicit version string. When omitted we attempt to
        infer it from ``package_path``.
    manifest_path:
        Optional path to the manifest. Defaults to ``<repo>/manifest.json``.
    """

    manifest_path = manifest_path or Path(__file__).resolve().parents[1] / "manifest.json"
    package_path = Path(package_path)
    if not package_path.exists():
        raise FileNotFoundError(f"Не найден артефакт сборки: {package_path}")

    manifest = _load_manifest(manifest_path)
    build_section: Dict[str, Any] = dict(manifest.get("build", {}))

    if version is None:
        version = _guess_version_from_package(package_path.name) or manifest.get("version")

    if version:
        manifest["version"] = version

    build_section["package_name"] = package_path.name
    manifest["build"] = build_section

    _dump_manifest(manifest_path, manifest)
    return manifest


__all__ = ["synchronize_manifest_with_build"]
