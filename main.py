# -*- coding: utf-8 -*-
"""CLI entry point for the refactored Detilda pipeline."""

from __future__ import annotations

from pathlib import Path

from core.pipeline import DetildaPipeline
from core.utils import ensure_dir


def main() -> None:
    version = "v5.0 refactored"
    pipeline = DetildaPipeline(version)

    workdir = Path("./_workdir")
    ensure_dir(workdir)

    print(f"=== Detilda {version} ===")
    print(f"Рабочая папка: {workdir.resolve()}")

    archive_name = input("Введите имя архива в ./_workdir (например, projectXXXX.zip): ").strip()
    email = input("Введите e-mail для отправки формы (по умолчанию r@prororo.com): ").strip() or "r@prororo.com"

    if not archive_name:
        print("❌ Имя архива не указано — завершение работы.")
        return

    archive_path = workdir / archive_name
    if not archive_path.exists():
        print(f"❌ Архив не найден: {archive_path}")
        return

    try:
        pipeline.run(archive_path, email)
    except Exception as exc:
        print(f"💥 Ошибка выполнения: {exc}")


if __name__ == "__main__":
    main()
