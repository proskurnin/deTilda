"""CLI entry point orchestrating the deTilda pipeline.

Читает manifest.json, запрашивает у пользователя имена архивов
и запускает DetildaPipeline для каждого из них.

Запуск:
    python main.py

Поддерживает несколько архивов за один запуск (через запятую).
При ошибке в одном архиве — переходит к следующему, не останавливается.
Завершается с кодом 1 если хотя бы один архив завершился с ошибкой.
"""
from __future__ import annotations

from pathlib import Path

from core import logger
from core.api import process_archive
from core.utils import ensure_dir, load_manifest
from core.version import APP_TITLE, APP_VERSION


def _prompt(prompt: str) -> str:
    """Обёртка над input() — перехватывает EOFError при неинтерактивном запуске."""
    try:
        return input(prompt)
    except EOFError:
        return ""


def _run_archive(
    archive_name: str,
    workdir: Path,
    logs_dir: Path,
) -> bool:
    """Запускает pipeline для одного архива. Возвращает True если успешно."""
    archive_path = workdir / archive_name
    if not archive_path.exists():
        print(f"❌ Архив не найден: {archive_path}")
        return False

    try:
        process_archive(archive_path, logs_dir=logs_dir)
        return True
    except Exception as exc:
        print(f"💥 Ошибка при обработке {archive_name}: {exc}")
        logger.exception(f"[cli] Ошибка при обработке архива {archive_name}")
        return False


def main() -> None:
    manifest = load_manifest()
    paths = manifest.get("paths", {})

    repo_root = Path(__file__).resolve().parent
    workdir = ensure_dir(repo_root / paths.get("workdir", "_workdir"))
    logs_dir = ensure_dir(repo_root / paths.get("logs", "logs"))

    print(f"=== {APP_TITLE} ===")
    print(f"Рабочая папка: {workdir.resolve()}")

    archive_input = _prompt(
        "Введите имя архива в ./_workdir (например, projectXXXX.zip). "
        "Можно перечислить несколько через запятую: "
    ).strip()

    if not archive_input:
        print("❌ Имя архива не указано — завершение работы.")
        return

    archive_names = [name.strip() for name in archive_input.split(",") if name.strip()]
    if not archive_names:
        print("❌ Имя архива не указано — завершение работы.")
        return

    had_errors = False
    for index, archive_name in enumerate(archive_names, start=1):
        if len(archive_names) > 1:
            print("======================================")
            print(f"▶️  {index}/{len(archive_names)}: обработка архива {archive_name}")

        had_errors = had_errors or not _run_archive(archive_name, workdir, logs_dir)

    if had_errors:
        raise SystemExit(1)
