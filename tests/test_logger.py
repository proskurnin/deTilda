"""Tests for core.logger — ContextVar isolation and basic logging."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import core.logger as logger


def test_contextvar_isolation_in_asyncio_tasks() -> None:
    """Два конкурентных asyncio-таска получают независимое состояние логгера.

    Доказывает, что конкурентные веб-запросы (v5) не будут мешать друг другу:
    project_name и logs_dir у каждого таска свои.
    """
    async def task_a() -> str:
        logger._project_name_var.set("project-A")
        await asyncio.sleep(0)  # yield — даём выполниться task_b
        return logger._project_name_var.get()

    async def task_b() -> str:
        logger._project_name_var.set("project-B")
        await asyncio.sleep(0)
        return logger._project_name_var.get()

    async def run() -> tuple[str, str]:
        return await asyncio.gather(
            asyncio.create_task(task_a()),
            asyncio.create_task(task_b()),
        )

    a, b = asyncio.run(run())
    assert a == "project-A"
    assert b == "project-B"



def test_attach_sets_project_name_for_current_context(tmp_path: Path) -> None:
    """attach_to_project() устанавливает project_name в текущем контексте."""
    logs_dir = tmp_path / "logs"
    logger.attach_to_project(tmp_path, logs_dir=logs_dir)
    assert logger.get_project_name() == tmp_path.name
    logger.close()
