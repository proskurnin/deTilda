"""CLI utility to bump the deTilda version using Semantic Versioning.

Usage:
    python tools/bump_version.py patch   # 4.7.0 → 4.7.1
    python tools/bump_version.py minor   # 4.7.0 → 4.8.0
    python tools/bump_version.py major   # 4.7.0 → 5.0.0

Options:
    --dry-run   Preview changes without writing anything
    --no-tag    Skip creating a git tag
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

MANIFEST_PATH = Path(__file__).resolve().parents[1] / "manifest.json"

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _save_manifest(data: dict) -> None:
    MANIFEST_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _parse_version(version_str: str) -> tuple[int, int, int]:
    match = _SEMVER_RE.match(version_str.strip())
    if not match:
        print(f"❌ Версия '{version_str}' не соответствует формату SemVer (X.Y.Z)")
        sys.exit(1)
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _bump(major: int, minor: int, patch: int, part: str) -> tuple[int, int, int]:
    if part == "major":
        return major + 1, 0, 0
    if part == "minor":
        return major, minor + 1, 0
    return major, minor, patch + 1


def _git_tag_exists(tag: str) -> bool:
    result = subprocess.run(
        ["git", "tag", "--list", tag],
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def _create_git_tag(tag: str, message: str) -> None:
    subprocess.run(["git", "tag", "-a", tag, "-m", message], check=True)
    print(f"🏷  Git тег создан: {tag}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "part",
        choices=["major", "minor", "patch"],
        help="Какой компонент версии поднять",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Показать что изменится, но ничего не записывать",
    )
    parser.add_argument(
        "--no-tag",
        action="store_true",
        help="Не создавать git тег",
    )
    args = parser.parse_args()

    manifest = _load_manifest()
    current = manifest.get("version", "")
    if not current:
        print("❌ Поле 'version' не найдено в manifest.json")
        sys.exit(1)

    major, minor, patch = _parse_version(current)
    new_major, new_minor, new_patch = _bump(major, minor, patch, args.part)
    new_version = f"{new_major}.{new_minor}.{new_patch}"
    new_date = date.today().isoformat()
    new_tag = f"v{new_version}"

    print(f"📦 Текущая версия : {current}")
    print(f"🚀 Новая версия   : {new_version}  ({args.part} bump)")
    print(f"📅 Дата релиза    : {new_date}")
    print(f"🏷  Git тег        : {new_tag}")

    if args.dry_run:
        print("\n⚠️  --dry-run: изменения не записаны.")
        return

    # Обновляем manifest.json
    manifest["version"] = new_version
    manifest["release_date"] = new_date
    if "build" in manifest:
        name = manifest["build"].get("package_name", "")
        # Заменяем старую версию в имени пакета если она там есть
        manifest["build"]["package_name"] = re.sub(
            r"\d+\.\d+\.\d+", new_version, name
        ) if name else f"detilda_{new_version}.zip"

    _save_manifest(manifest)
    print(f"\n✅ manifest.json обновлён: {current} → {new_version}")

    # Создаём git тег
    if not args.no_tag:
        if _git_tag_exists(new_tag):
            print(f"⚠️  Тег {new_tag} уже существует — пропускаю.")
        else:
            _create_git_tag(new_tag, f"deTilda {new_version}")


if __name__ == "__main__":
    main()
