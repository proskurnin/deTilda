"""CLI utility to sync ``manifest.json`` with the produced build artefact."""
from __future__ import annotations

import argparse
from pathlib import Path

from core.build_sync import synchronize_manifest_with_build


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "package",
        type=Path,
        help="Path to the generated build archive (e.g. dist/detilda_vX.zip)",
    )
    parser.add_argument(
        "--version",
        dest="version",
        help="Optional explicit version that should be stored in manifest.json",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Path to manifest.json (defaults to repository root)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    synchronize_manifest_with_build(
        package_path=args.package,
        version=args.version,
        manifest_path=args.manifest,
    )


if __name__ == "__main__":
    main()
