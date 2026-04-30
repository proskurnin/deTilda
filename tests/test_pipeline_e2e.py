"""End-to-end smoke test for DetildaPipeline.

Создаёт минимальный ZIP-архив с одной HTML-страницей и CSS-файлом,
содержащими tilda-артефакты, и прогоняет весь конвейер.

Цель: убедиться, что pipeline.run() не бросает исключений и возвращает
корректный PipelineStats даже если конфиг берётся из реального config.yaml.
"""
from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.pipeline import DetildaPipeline, PipelineStats

_HTML = """\
<!DOCTYPE html>
<html>
<head>
<title>Test Site</title>
<link rel="stylesheet" href="css/tildasite.css">
<link rel="icon" href="/favicon.ico">
</head>
<body>
<div class="t-rec">
  <img src="images/tildacopy.png" alt="">
</div>
<script src="js/tilda-stat-1.0.min.js"></script>
</body>
</html>
"""

_CSS = """\
.t-rec { font-family: 'TildaSans', sans-serif; }
"""


@pytest.fixture()
def minimal_zip(tmp_path: Path) -> Path:
    """Возвращает путь к минимальному Tilda-архиву в tmp_path/_workdir/."""
    workdir = tmp_path / "_workdir"
    workdir.mkdir()

    # Реальные config/ и resources/ нужны для корректной работы шагов конвейера.
    # Symlinking позволяет избежать копирования нескольких MB и гарантирует,
    # что тест всегда использует актуальный конфиг.
    for subdir in ("config", "resources"):
        src = ROOT / subdir
        if src.exists():
            (tmp_path / subdir).symlink_to(src)

    zip_path = workdir / "mysite.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("mysite/index.html", _HTML)
        zf.writestr("mysite/css/tildasite.css", _CSS)

    return zip_path


def test_pipeline_runs_without_exception(minimal_zip: Path, tmp_path: Path) -> None:
    """Pipeline завершается без исключений на минимальном архиве."""
    pipeline = DetildaPipeline(logs_dir=tmp_path / "logs")
    stats = pipeline.run(minimal_zip)

    assert isinstance(stats, PipelineStats)
    assert stats.exec_time > 0


def test_pipeline_renames_tilda_assets(minimal_zip: Path, tmp_path: Path) -> None:
    """Шаг assets переименовывает tilda-файлы (til→ai)."""
    pipeline = DetildaPipeline(logs_dir=tmp_path / "logs")
    stats = pipeline.run(minimal_zip)

    project_root = minimal_zip.parent / "mysite"
    assert (project_root / "css" / "aidasite.css").exists()
    assert not (project_root / "css" / "tildasite.css").exists()
    assert stats.renamed_assets >= 1


def test_pipeline_step_error_doesnt_abort(minimal_zip: Path, tmp_path: Path, monkeypatch) -> None:
    """Ошибка в одном шаге не прерывает весь конвейер."""
    import core.page404 as page404_mod

    def _boom(project_root):
        raise RuntimeError("simulated step failure")

    monkeypatch.setattr(page404_mod, "update_404_page", _boom)

    pipeline = DetildaPipeline(logs_dir=tmp_path / "logs")
    stats = pipeline.run(minimal_zip)

    assert isinstance(stats, PipelineStats)
    assert stats.warnings >= 1


def test_pipeline_dry_run_does_not_modify_files(minimal_zip: Path, tmp_path: Path) -> None:
    """В режиме dry_run safe_write/copy/delete подавляются — текст файлов не изменяется.

    Замечание: assets переименовывает файлы через Path.rename(), что сознательно
    не блокируется dry_run — переименование безопасно обратимо. Содержимое файлов
    (font-family замена, refs, inject) не изменяется.
    """
    pipeline = DetildaPipeline(logs_dir=tmp_path / "logs", dry_run=True)
    stats = pipeline.run(minimal_zip)

    assert isinstance(stats, PipelineStats)

    # assets переименовал через Path.rename() → aidasite.css существует
    css_path = minimal_zip.parent / "mysite" / "css" / "aidasite.css"
    assert css_path.exists()

    # font_substitute вызвал safe_write (подавлен) → содержимое не изменено
    # Оригинал содержит 'TildaSans'; в normal-режиме было бы 'Manrope'
    assert "TildaSans" in css_path.read_text(encoding="utf-8")

    # inject вызвал safe_write (подавлен) → form-handler.js не добавлен в index.html
    html_path = minimal_zip.parent / "mysite" / "index.html"
    assert "form-handler.js" not in html_path.read_text(encoding="utf-8")
