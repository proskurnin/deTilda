"""Tests for ProcessParams — email routing through pipeline."""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.api import process_archive
from core.params import ProcessParams


@pytest.fixture()
def minimal_zip(tmp_path: Path) -> Path:
    workdir = tmp_path / "_workdir"
    workdir.mkdir()
    for subdir in ("config", "resources"):
        src = ROOT / subdir
        if src.exists():
            (tmp_path / subdir).symlink_to(src)
    zip_path = workdir / "site.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("site/index.html", "<html><body>hi</body></html>")
    return zip_path


def test_params_email_written_to_send_email_php(minimal_zip: Path, tmp_path: Path) -> None:
    """Email из ProcessParams попадает в send_email.php."""
    process_archive(
        minimal_zip,
        params=ProcessParams(email="owner@example.com"),
        logs_dir=tmp_path / "logs",
    )
    php = minimal_zip.parent / "site" / "send_email.php"
    assert php.exists()
    assert "owner@example.com" in php.read_text(encoding="utf-8")


def test_empty_email_falls_back_to_config(minimal_zip: Path, tmp_path: Path) -> None:
    """Пустой email → используются test_recipients из config.yaml."""
    process_archive(
        minimal_zip,
        params=ProcessParams(email=""),
        logs_dir=tmp_path / "logs",
    )
    php = minimal_zip.parent / "site" / "send_email.php"
    assert php.exists()
    # config.yaml → forms.test_recipients = ["r@prororo.com"]
    assert "r@prororo.com" in php.read_text(encoding="utf-8")


def test_no_params_falls_back_to_config(minimal_zip: Path, tmp_path: Path) -> None:
    """params=None → поведение как раньше, конфиг используется."""
    process_archive(minimal_zip, logs_dir=tmp_path / "logs")
    php = minimal_zip.parent / "site" / "send_email.php"
    assert "r@prororo.com" in php.read_text(encoding="utf-8")
