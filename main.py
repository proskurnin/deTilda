# -*- coding: utf-8 -*-
"""CLI entry point orchestrating the Detilda pipeline."""
# TODO: [26.10.2025] Разобраться с регистром урлов. При проверке относительных урлов указанных в htaccess в нижнем регистре мы получаем ошибку если в коде регистр отличается. Пример href="/Job" в логе ⚠️ [checker] Битая ссылка в page24165416.html: /Job
# TODO: [04.02.2026] Добавить единый универсальный send_email.php (брать из alliance-trd.com)
# TODO: [04.02.2026]

from __future__ import annotations

from pathlib import Path

from core.pipeline import DetildaPipeline
from core.utils import ensure_dir, load_manifest
from core.version import APP_VERSION

VERSION = APP_VERSION


def _prompt(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""


def _process_archive(
    archive_name: str,
    workdir: Path,
    email: str,
    version: str,
) -> None:
    archive_path = workdir / archive_name
    if not archive_path.exists():
        print(f"❌ Архив не найден: {archive_path}")
        return
    pipeline = DetildaPipeline(version=version)
    pipeline.run(archive_path, email)


def main() -> None:
    manifest = load_manifest()
    version = manifest.get("version", VERSION)
    workdir = ensure_dir(Path(manifest.get("paths", {}).get("workdir", "_workdir")))

    print(f"=== Detilda {version} ===")
    print(f"Рабочая папка: {workdir.resolve()}")

    archive_prompt = (
        "Введите имя архива в ./_workdir (например, projectXXXX.zip). "
        "Можно перечислить несколько через запятую: "
    )
    archive_input = _prompt(archive_prompt).strip()
    if not archive_input:
        print("❌ Имя архива не указано — завершение работы.")
        return

    archive_names = [name.strip() for name in archive_input.split(",") if name.strip()]
    if not archive_names:
        print("❌ Имя архива не указано — завершение работы.")
        return

    email = str(manifest.get("default_email", "r@prororo.com")).strip() or "r@prororo.com"
    print(f"E-mail для форм: {email}")

    for index, archive_name in enumerate(archive_names, start=1):
        if len(archive_names) > 1:
            print("======================================")
            print(f"▶️  {index}/{len(archive_names)}: обработка архива {archive_name}")

        _process_archive(archive_name, workdir, email, version)


if __name__ == "__main__":
    main()
