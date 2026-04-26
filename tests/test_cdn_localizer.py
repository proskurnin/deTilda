"""Tests for core.cdn_localizer — replace remaining tildacdn/aidacdn URLs."""
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

from core import cdn_localizer, downloader


def test_replaces_direct_url_in_js(tmp_path: Path, monkeypatch) -> None:
    """Прямой URL https://static.tildacdn.com/path/file.png заменяется на локальный путь."""
    js = tmp_path / "js" / "test.js"
    js.parent.mkdir()
    js.write_text(
        'var url = "https://static.tildacdn.com/lib/flags/flags7.png";',
        encoding="utf-8",
    )

    monkeypatch.setattr(downloader, "fetch_bytes", lambda _url, **_kw: (b"png-bytes", False))
    monkeypatch.setattr(cdn_localizer, "fetch_bytes", downloader.fetch_bytes)

    result = cdn_localizer.localize_cdn_urls(tmp_path)

    text = js.read_text(encoding="utf-8")
    assert "tildacdn.com" not in text
    assert '"lib/flags/flags7.png"' in text
    assert (tmp_path / "lib" / "flags" / "flags7.png").exists()
    assert result.urls_localized >= 1


def test_replaces_aidacdn_url(tmp_path: Path, monkeypatch) -> None:
    """После til→ai URL становится aidacdn — тоже обрабатывается."""
    js = tmp_path / "js" / "test.js"
    js.parent.mkdir()
    js.write_text(
        'var url = "https://static.aidacdn.com/lib/flags/flags7.png";',
        encoding="utf-8",
    )
    monkeypatch.setattr(downloader, "fetch_bytes", lambda _url, **_kw: (b"png", False))
    monkeypatch.setattr(cdn_localizer, "fetch_bytes", downloader.fetch_bytes)

    cdn_localizer.localize_cdn_urls(tmp_path)

    text = js.read_text(encoding="utf-8")
    assert "aidacdn.com" not in text
    assert '"lib/flags/flags7.png"' in text


def test_replaces_concatenated_url_in_js(tmp_path: Path, monkeypatch) -> None:
    """Конкатенация 'https://static.aidacdn.' + zone() + '/path/file.png' заменяется."""
    js = tmp_path / "phone.js"
    js.write_text(
        'var s = "background-image:url(https://static.aidacdn." + t_zone() + "/lib/flags/flags7.png)"',
        encoding="utf-8",
    )
    monkeypatch.setattr(downloader, "fetch_bytes", lambda _url, **_kw: (b"png", False))
    monkeypatch.setattr(cdn_localizer, "fetch_bytes", downloader.fetch_bytes)

    cdn_localizer.localize_cdn_urls(tmp_path)

    text = js.read_text(encoding="utf-8")
    # Конкатенация заменена на статичный относительный путь
    assert "aidacdn" not in text
    assert "lib/flags/flags7.png" in text
    assert (tmp_path / "lib" / "flags" / "flags7.png").exists()


def test_processes_css_files(tmp_path: Path, monkeypatch) -> None:
    """CSS-файлы тоже обрабатываются."""
    css = tmp_path / "css" / "main.css"
    css.parent.mkdir()
    css.write_text(
        ".x { background: url(https://static.tildacdn.com/img/icon.svg); }",
        encoding="utf-8",
    )
    monkeypatch.setattr(downloader, "fetch_bytes", lambda _url, **_kw: (b"svg", False))
    monkeypatch.setattr(cdn_localizer, "fetch_bytes", downloader.fetch_bytes)

    cdn_localizer.localize_cdn_urls(tmp_path)

    text = css.read_text(encoding="utf-8")
    assert "tildacdn.com" not in text
    assert "img/icon.svg" in text


def test_keeps_url_when_download_fails(tmp_path: Path, monkeypatch) -> None:
    """Если скачать не удалось — URL остаётся как был, не ломаем JS."""
    import urllib.error

    js = tmp_path / "test.js"
    js.write_text('var u = "https://static.tildacdn.com/lib/missing.png";', encoding="utf-8")

    def _fail(*_args, **_kw):
        raise urllib.error.URLError("network")

    monkeypatch.setattr(downloader, "fetch_bytes", _fail)
    monkeypatch.setattr(cdn_localizer, "fetch_bytes", downloader.fetch_bytes)

    cdn_localizer.localize_cdn_urls(tmp_path)

    # URL остался — лучше работающий код с тильдой, чем сломанный без
    text = js.read_text(encoding="utf-8")
    assert "tildacdn.com" in text


def test_caches_downloads(tmp_path: Path, monkeypatch) -> None:
    """Один и тот же файл из разных мест скачивается только один раз."""
    (tmp_path / "a.js").write_text(
        'var x = "https://static.tildacdn.com/lib/flags/flags7.png";', encoding="utf-8"
    )
    (tmp_path / "b.js").write_text(
        'var y = "https://static.tildacdn.com/lib/flags/flags7.png";', encoding="utf-8"
    )

    call_count = {"n": 0}
    def _counting_fetch(_url, **_kw):
        call_count["n"] += 1
        return (b"png", False)
    monkeypatch.setattr(downloader, "fetch_bytes", _counting_fetch)
    monkeypatch.setattr(cdn_localizer, "fetch_bytes", downloader.fetch_bytes)

    cdn_localizer.localize_cdn_urls(tmp_path)
    assert call_count["n"] == 1


def test_falls_back_to_reversed_path_on_404(tmp_path: Path, monkeypatch) -> None:
    """Если URL с aida даёт 404 — пробуем с заменой aida→tilda."""
    import urllib.error

    js = tmp_path / "test.js"
    js.write_text(
        'var u = "https://static.aidacdn.com/fonts/aidasans/aidasans-vf.woff2";',
        encoding="utf-8",
    )

    fetched_urls: list[str] = []
    def _fetch(url, **_kw):
        fetched_urls.append(url)
        if "aidasans" in url:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return (b"font", False)

    monkeypatch.setattr(downloader, "fetch_bytes", _fetch)
    monkeypatch.setattr(cdn_localizer, "fetch_bytes", downloader.fetch_bytes)

    cdn_localizer.localize_cdn_urls(tmp_path)

    # Сначала запрос с aidasans → 404, потом с tildasans → успех
    assert any("aidasans" in u for u in fetched_urls)
    assert any("tildasans" in u for u in fetched_urls)
    # Файл сохранён по original path (с aida — как в JS)
    assert (tmp_path / "fonts" / "aidasans" / "aidasans-vf.woff2").exists()
    # JS обновлён на относительный путь
    text = js.read_text(encoding="utf-8")
    assert "aidacdn.com" not in text
    assert "fonts/aidasans/aidasans-vf.woff2" in text


# ----- Тесты для cleanup_unresolved_cdn_references -----

def test_cleanup_removes_font_face_block_with_cdn_url(tmp_path: Path) -> None:
    """@font-face с tildacdn URL удаляется целиком."""
    css = tmp_path / "fonts.css"
    css.write_text(
        "@font-face {\n"
        "  font-family: 'TildaSans';\n"
        "  src: url('https://static.tildacdn.com/fonts/x.woff2');\n"
        "}\n"
        "body { color: red; }\n",
        encoding="utf-8",
    )
    result = cdn_localizer.cleanup_unresolved_cdn_references(tmp_path)
    text = css.read_text(encoding="utf-8")
    assert "@font-face" not in text
    assert "body { color: red; }" in text  # остальное не тронуто
    assert result.font_faces_removed == 1


def test_cleanup_keeps_clean_font_face(tmp_path: Path) -> None:
    """@font-face без tilda/aida URL не трогается."""
    css = tmp_path / "fonts.css"
    css.write_text(
        "@font-face { src: url('fonts/local.woff2'); }",
        encoding="utf-8",
    )
    cdn_localizer.cleanup_unresolved_cdn_references(tmp_path)
    text = css.read_text(encoding="utf-8")
    assert "@font-face" in text
    assert "local.woff2" in text


def test_cleanup_removes_script_with_cdn_src(tmp_path: Path) -> None:
    """<script src='...cdn...'></script> удаляется."""
    html = tmp_path / "index.html"
    html.write_text(
        '<head>\n'
        '<script src="https://neo.aidacdn.com/js/aida-fallback.js" async></script>\n'
        '<script src="js/local.js"></script>\n'
        '</head>',
        encoding="utf-8",
    )
    result = cdn_localizer.cleanup_unresolved_cdn_references(tmp_path)
    text = html.read_text(encoding="utf-8")
    assert "aidacdn.com" not in text
    assert "local.js" in text  # локальные не трогаем
    assert result.scripts_removed == 1


def test_cleanup_keeps_dns_prefetch_link(tmp_path: Path) -> None:
    """<link rel='dns-prefetch'> с cdn оставляется — это безопасный хинт."""
    html = tmp_path / "index.html"
    html.write_text(
        '<link rel="dns-prefetch" href="https://ws.aidacdn.com">',
        encoding="utf-8",
    )
    cdn_localizer.cleanup_unresolved_cdn_references(tmp_path)
    text = html.read_text(encoding="utf-8")
    # dns-prefetch не блокирует — оставляем
    assert "dns-prefetch" in text
    assert "aidacdn.com" in text


def test_cleanup_removes_stylesheet_link_with_cdn(tmp_path: Path) -> None:
    """<link rel='stylesheet' href='...cdn...'> удаляется (блокирует рендер)."""
    html = tmp_path / "index.html"
    html.write_text(
        '<link rel="stylesheet" href="https://static.aidacdn.com/css/x.css">',
        encoding="utf-8",
    )
    cdn_localizer.cleanup_unresolved_cdn_references(tmp_path)
    text = html.read_text(encoding="utf-8")
    assert "aidacdn.com" not in text


def test_negative_cache_skips_repeated_failed_path(tmp_path: Path, monkeypatch) -> None:
    """Один и тот же неудачный path не качается повторно (negative cache)."""
    import urllib.error

    # Два файла, оба ссылаются на одну и ту же недоступную картинку
    (tmp_path / "a.html").write_text(
        '<link href="https://static.tildacdn.com/missing/x.png">', encoding="utf-8"
    )
    (tmp_path / "b.html").write_text(
        '<link href="https://static.tildacdn.com/missing/x.png">', encoding="utf-8"
    )

    call_count = {"n": 0}
    def _always_404(_url, **_kw):
        call_count["n"] += 1
        raise urllib.error.HTTPError(_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(downloader, "fetch_bytes", _always_404)
    monkeypatch.setattr(cdn_localizer, "fetch_bytes", downloader.fetch_bytes)

    cdn_localizer.localize_cdn_urls(tmp_path)

    # Один URL → одна попытка с aida path → одна с reverse path = 2 запроса всего
    # А не 4 (двойное обращение от двух файлов)
    assert call_count["n"] <= 2, f"Слишком много повторных попыток: {call_count['n']}"
