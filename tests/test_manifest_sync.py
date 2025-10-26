from __future__ import annotations

import json
from pathlib import Path

from core.build_sync import synchronize_manifest_with_build


def _write_manifest(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def test_synchronize_manifest_updates_version_and_package(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        {
            "name": "Detilda",
            "version": "v4.4",
            "build": {"package_name": "detilda_v4.4.zip"},
        },
    )

    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    package_path = dist_dir / "detilda_v4.5_LTS_unified.zip"
    package_path.write_bytes(b"")

    result = synchronize_manifest_with_build(
        package_path=package_path,
        manifest_path=manifest_path,
    )

    assert result["version"] == "v4.5 LTS unified"
    assert result["build"]["package_name"] == "detilda_v4.5_LTS_unified.zip"

    stored = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert stored == result


def test_synchronize_manifest_respects_explicit_version(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        {
            "name": "Detilda",
            "version": "v4.4",
            "build": {"package_name": "detilda_v4.4.zip"},
        },
    )

    package_path = tmp_path / "detilda_v4.6.zip"
    package_path.write_bytes(b"")

    result = synchronize_manifest_with_build(
        package_path=package_path,
        version="v4.6.1 stable",
        manifest_path=manifest_path,
    )

    assert result["version"] == "v4.6.1 stable"
    assert result["build"]["package_name"] == "detilda_v4.6.zip"
