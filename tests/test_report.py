"""Tests for core.report — generates intermediate and final reports."""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "yaml" not in sys.modules:
    yaml_stub = types.ModuleType("yaml")
    yaml_stub.safe_load = lambda *_args, **_kwargs: {}
    sys.modules["yaml"] = yaml_stub

from core import logger, report
from core.htaccess import MissingRouteInfo


def _setup_logger(tmp_path: Path) -> Path:
    """Подменяет состояние логгера, чтобы отчёты писались в tmp_path."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    logger._project_name = "test_project"
    logger._logs_dir = logs_dir
    return logs_dir


def _enable_reports() -> None:
    """Сбрасывает кеш и принудительно включает отчёты."""
    report._REPORTS_ENABLED = True


def _disable_reports() -> None:
    report._REPORTS_ENABLED = False


def test_intermediate_report_contains_stats(tmp_path: Path, monkeypatch) -> None:
    logs_dir = _setup_logger(tmp_path)
    _enable_reports()

    report.generate_intermediate_report(renamed=10, cleaned=5, fixed_links=20, broken_links=2)

    report_path = logs_dir / "test_project_detilda_report.txt"
    assert report_path.exists()
    text = report_path.read_text(encoding="utf-8")
    assert "Переименовано ассетов: 10" in text
    assert "Очищено файлов: 5" in text
    assert "Исправлено ссылок: 20" in text
    assert "битых ссылок: 2" in text


def test_intermediate_report_overwrites(tmp_path: Path) -> None:
    """Каждый вызов перезаписывает предыдущий — пишется текущее состояние."""
    logs_dir = _setup_logger(tmp_path)
    _enable_reports()

    report.generate_intermediate_report(renamed=1, cleaned=0, fixed_links=0, broken_links=0)
    report.generate_intermediate_report(renamed=99, cleaned=99, fixed_links=99, broken_links=0)

    text = (logs_dir / "test_project_detilda_report.txt").read_text(encoding="utf-8")
    assert "99" in text
    assert "Переименовано ассетов: 1" not in text  # старое значение перезаписано


def test_final_report_status_success(tmp_path: Path) -> None:
    logs_dir = _setup_logger(tmp_path)
    _enable_reports()

    report.generate_final_report(
        project_root=tmp_path, cleaned_count=1, renamed_count=1, formatted_html_files=1,
        warnings=0, errors=0, broken_links_fixed=10, broken_links_left=0,
        htaccess_routes_initially_broken=0, htaccess_routes_autofixed=0,
        broken_htaccess_routes=0, downloaded_remote_assets=0, ssl_bypass_downloads=0,
        forms_found=2, forms_hooked=2, tilda_remnants=0,
        missing_htaccess_routes=[], exec_time=1.5,
    )

    text = (logs_dir / "test_project_final_report.txt").read_text(encoding="utf-8")
    assert "✅" in text
    assert "завершено успешно" in text
    assert "Остатков Tilda в ссылках: 0" in text


def test_final_report_status_warnings(tmp_path: Path) -> None:
    logs_dir = _setup_logger(tmp_path)
    _enable_reports()

    report.generate_final_report(
        project_root=tmp_path, cleaned_count=0, renamed_count=0, formatted_html_files=0,
        warnings=3, errors=0, broken_links_fixed=0, broken_links_left=0,
        htaccess_routes_initially_broken=0, htaccess_routes_autofixed=0,
        broken_htaccess_routes=0, downloaded_remote_assets=0, ssl_bypass_downloads=0,
        forms_found=0, forms_hooked=0, tilda_remnants=0,
        missing_htaccess_routes=[], exec_time=1.0,
    )

    text = (logs_dir / "test_project_final_report.txt").read_text(encoding="utf-8")
    assert "⚠️" in text
    assert "завершено с предупреждениями" in text


def test_final_report_status_errors(tmp_path: Path) -> None:
    logs_dir = _setup_logger(tmp_path)
    _enable_reports()

    report.generate_final_report(
        project_root=tmp_path, cleaned_count=0, renamed_count=0, formatted_html_files=0,
        warnings=0, errors=2, broken_links_fixed=0, broken_links_left=0,
        htaccess_routes_initially_broken=0, htaccess_routes_autofixed=0,
        broken_htaccess_routes=0, downloaded_remote_assets=0, ssl_bypass_downloads=0,
        forms_found=0, forms_hooked=0, tilda_remnants=0,
        missing_htaccess_routes=[], exec_time=1.0,
    )

    text = (logs_dir / "test_project_final_report.txt").read_text(encoding="utf-8")
    assert "❌" in text
    assert "завершено с ошибками" in text


def test_final_report_lists_missing_routes(tmp_path: Path) -> None:
    logs_dir = _setup_logger(tmp_path)
    _enable_reports()

    missing = [
        MissingRouteInfo(alias="/foo", target="missing.html", action="removed", replacement=None),
        MissingRouteInfo(alias="/bar", target="bar.html", action="stub_created", replacement="bar.html"),
    ]
    report.generate_final_report(
        project_root=tmp_path, cleaned_count=0, renamed_count=0, formatted_html_files=0,
        warnings=0, errors=0, broken_links_fixed=0, broken_links_left=0,
        htaccess_routes_initially_broken=2, htaccess_routes_autofixed=2,
        broken_htaccess_routes=0, downloaded_remote_assets=0, ssl_bypass_downloads=0,
        forms_found=0, forms_hooked=0, tilda_remnants=0,
        missing_htaccess_routes=missing, exec_time=1.0,
    )

    text = (logs_dir / "test_project_final_report.txt").read_text(encoding="utf-8")
    assert "/foo -> missing.html [removed]" in text
    assert "/bar -> bar.html [stub_created: bar.html]" in text


def test_tilda_remnants_zero_shows_check(tmp_path: Path) -> None:
    logs_dir = _setup_logger(tmp_path)
    _enable_reports()

    report.generate_final_report(
        project_root=tmp_path, cleaned_count=0, renamed_count=0, formatted_html_files=0,
        warnings=0, errors=0, broken_links_fixed=0, broken_links_left=0,
        htaccess_routes_initially_broken=0, htaccess_routes_autofixed=0,
        broken_htaccess_routes=0, downloaded_remote_assets=0, ssl_bypass_downloads=0,
        forms_found=0, forms_hooked=0, tilda_remnants=0,
        missing_htaccess_routes=[], exec_time=1.0,
    )

    text = (logs_dir / "test_project_final_report.txt").read_text(encoding="utf-8")
    assert "✅ Остатков Tilda в ссылках: 0" in text


def test_tilda_remnants_nonzero_shows_cross(tmp_path: Path) -> None:
    logs_dir = _setup_logger(tmp_path)
    _enable_reports()

    report.generate_final_report(
        project_root=tmp_path, cleaned_count=0, renamed_count=0, formatted_html_files=0,
        warnings=5, errors=0, broken_links_fixed=0, broken_links_left=0,
        htaccess_routes_initially_broken=0, htaccess_routes_autofixed=0,
        broken_htaccess_routes=0, downloaded_remote_assets=0, ssl_bypass_downloads=0,
        forms_found=0, forms_hooked=0, tilda_remnants=5,
        missing_htaccess_routes=[], exec_time=1.0,
    )

    text = (logs_dir / "test_project_final_report.txt").read_text(encoding="utf-8")
    assert "❌ Остатков Tilda в ссылках: 5" in text


def test_reports_disabled_skips_writing(tmp_path: Path) -> None:
    logs_dir = _setup_logger(tmp_path)
    _disable_reports()

    report.generate_intermediate_report(renamed=1, cleaned=1, fixed_links=1, broken_links=0)
    report.generate_final_report(
        project_root=tmp_path, cleaned_count=0, renamed_count=0, formatted_html_files=0,
        warnings=0, errors=0, broken_links_fixed=0, broken_links_left=0,
        htaccess_routes_initially_broken=0, htaccess_routes_autofixed=0,
        broken_htaccess_routes=0, downloaded_remote_assets=0, ssl_bypass_downloads=0,
        forms_found=0, forms_hooked=0, tilda_remnants=0,
        missing_htaccess_routes=[], exec_time=1.0,
    )

    assert not (logs_dir / "test_project_detilda_report.txt").exists()
    assert not (logs_dir / "test_project_final_report.txt").exists()
    # Восстанавливаем для других тестов
    _enable_reports()
