from pathlib import Path

from core import downloader, fonts_localizer


def test_localize_inlines_google_import_and_downloads_font(tmp_path, monkeypatch):
    css_dir = tmp_path / "css"
    css_dir.mkdir(parents=True)
    css_path = css_dir / "style.css"
    css_path.write_text(
        "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400');\nbody{margin:0}",
        encoding="utf-8",
    )

    # Патчим в downloader, потому что fonts_localizer импортирует оттуда
    monkeypatch.setattr(
        downloader,
        "fetch_text",
        lambda _url, **_kw: "@font-face{src:url(https://fonts.gstatic.com/s/inter/v1/inter.woff2) format('woff2');}",
    )
    monkeypatch.setattr(
        downloader, "fetch_bytes", lambda _url, **_kw: (b"font-data", False)
    )
    # Патчим импортированные имена в fonts_localizer
    monkeypatch.setattr(fonts_localizer, "fetch_text", downloader.fetch_text)
    monkeypatch.setattr(fonts_localizer, "fetch_bytes", downloader.fetch_bytes)

    updated, imports, downloaded = fonts_localizer.localize_google_fonts(tmp_path)

    assert updated == 1
    assert imports == 1
    assert downloaded == 1

    updated_css = css_path.read_text(encoding="utf-8")
    assert "@import" not in updated_css
    assert "../fonts/google/" in updated_css

    font_files = list((tmp_path / "fonts" / "google").glob("*.woff2"))
    assert len(font_files) == 1
    assert font_files[0].read_bytes() == b"font-data"


def test_localize_direct_gstatic_url(tmp_path, monkeypatch):
    css_path = tmp_path / "style.css"
    css_path.write_text(
        "@font-face{src:url(https://fonts.gstatic.com/s/roboto/v1/roboto.woff2)}",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        downloader, "fetch_bytes", lambda _url, **_kw: (b"font-data", False)
    )
    monkeypatch.setattr(fonts_localizer, "fetch_bytes", downloader.fetch_bytes)

    updated, imports, downloaded = fonts_localizer.localize_google_fonts(tmp_path)

    assert updated == 1
    assert imports == 0
    assert downloaded == 1
    updated_css = css_path.read_text(encoding="utf-8")
    assert "fonts.gstatic.com" not in updated_css
    assert "fonts/google/" in updated_css
