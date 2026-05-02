"""Tests for detailed web job result metadata."""
from __future__ import annotations

from core.pipeline import PipelineStats
from web.worker import _build_stats_details, _collect_log_messages


def test_collect_log_messages_extracts_warnings_and_errors(tmp_path) -> None:
    log_path = tmp_path / "job_detilda.log"
    log_path.write_text(
        "\n".join(
            [
                "2026-05-02 10:00:00 ℹ️ обычная строка",
                "2026-05-02 10:00:01 ⚠️ [checker] Битая ссылка: missing.html",
                "2026-05-02 10:00:02 💥 [pipeline] Шаг forms завершился с ошибкой: boom",
                "2026-05-02 10:00:03 ⚠️ Предупреждений: 1",
                "2026-05-02 10:00:04 ⛔ Ошибок: 1",
            ]
        ),
        encoding="utf-8",
    )

    messages = _collect_log_messages(tmp_path)

    assert messages["warnings"] == ["⚠️ [checker] Битая ссылка: missing.html"]
    assert messages["errors"] == ["💥 [pipeline] Шаг forms завершился с ошибкой: boom"]


def test_build_stats_details_includes_pipeline_counters_and_log_messages(tmp_path) -> None:
    (tmp_path / "job_detilda.log").write_text(
        "2026-05-02 10:00:01 ⚠️ [images] unresolved image: bg.jpg\n",
        encoding="utf-8",
    )
    stats = PipelineStats(
        renamed_assets=29,
        removed_assets=2,
        fixed_links=2990,
        broken_links=1,
        downloaded_remote_assets=1,
        forms_found=6,
        forms_hooked=6,
        warnings=1,
        errors=0,
        images_unresolved=1,
    )

    details = _build_stats_details(stats, tmp_path)

    assert "Переименовано ассетов: 29" in details["renamed_assets"]["items"]
    assert "Исправлено ссылок: 2990" in details["fixed_links"]["items"]
    assert "Загружено удалённых ассетов: 1" in details["downloaded"]["items"]
    assert "Форм найдено: 6" in details["forms_hooked"]["items"]
    assert "Потенциально неразрешённых изображений: 1" in details["warnings"]["items"]
    assert "⚠️ [images] unresolved image: bg.jpg" in details["warnings"]["items"]
    assert details["errors"]["items"] == ["Ошибок нет."]
