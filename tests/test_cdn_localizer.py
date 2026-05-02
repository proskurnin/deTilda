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


def test_replaces_protocol_relative_url(tmp_path: Path, monkeypatch) -> None:
    """Protocol-relative CDN URLs are treated as https resources."""
    html = tmp_path / "index.html"
    html.write_text('<script src="//static.tildacdn.com/js/tilda-extra.js"></script>', encoding="utf-8")

    monkeypatch.setattr(downloader, "fetch_bytes", lambda _url, **_kw: (b"js", False))
    monkeypatch.setattr(cdn_localizer, "fetch_bytes", downloader.fetch_bytes)

    result = cdn_localizer.localize_cdn_urls(tmp_path)

    text = html.read_text(encoding="utf-8")
    assert "static.tildacdn.com" not in text
    assert 'src="js/tilda-extra.js"' in text
    assert (tmp_path / "js" / "tilda-extra.js").exists()
    assert result.urls_localized == 1


def test_direct_url_query_is_not_used_as_local_filename(tmp_path: Path, monkeypatch) -> None:
    """Cache-busting query strings are stripped when saving a CDN file."""
    js = tmp_path / "test.js"
    js.write_text(
        'var src = "https://static.tildacdn.com/js/tilda-extra.js?t=123";',
        encoding="utf-8",
    )

    monkeypatch.setattr(downloader, "fetch_bytes", lambda _url, **_kw: (b"js", False))
    monkeypatch.setattr(cdn_localizer, "fetch_bytes", downloader.fetch_bytes)

    cdn_localizer.localize_cdn_urls(tmp_path)

    text = js.read_text(encoding="utf-8")
    assert "tildacdn.com" not in text
    assert '"js/tilda-extra.js"' in text
    assert (tmp_path / "js" / "tilda-extra.js").exists()
    assert not (tmp_path / "js" / "tilda-extra.js?t=123").exists()


def test_dynamic_script_src_assignment_is_localized(tmp_path: Path, monkeypatch) -> None:
    """Script URLs assigned after createElement are still direct CDN strings."""
    js = tmp_path / "loader.js"
    js.write_text(
        "var s = document.createElement('script');"
        "s.src = 'https://static.tildacdn.com/js/tilda-extra.js';"
        "document.head.appendChild(s);",
        encoding="utf-8",
    )

    monkeypatch.setattr(downloader, "fetch_bytes", lambda _url, **_kw: (b"js", False))
    monkeypatch.setattr(cdn_localizer, "fetch_bytes", downloader.fetch_bytes)

    cdn_localizer.localize_cdn_urls(tmp_path)

    text = js.read_text(encoding="utf-8")
    assert "static.tildacdn.com" not in text
    assert "s.src = 'js/tilda-extra.js'" in text
    assert (tmp_path / "js" / "tilda-extra.js").exists()


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


def test_keeps_dynamic_runtime_cdn_base_in_js(tmp_path: Path, monkeypatch) -> None:
    """Не ломает runtime, где CDN-домен собирается отдельно от имени ресурса."""
    js_dir = tmp_path / "js"
    js_dir.mkdir()
    js = js_dir / "aida-zero-forms-1.0.min.js"
    source = (
        'function add(o,n){var s=true,_="",d="https://static.aidacdn."+getRootZone();'
        '!s&&_&&-1!==_.indexOf("https://")&&(d=_.split("/js/")[0]);'
        'var c=document.createElement(n);'
        'c.id="x","script"===n?(c.src=d+"/js/"+o,c.async=!0):'
        '"link"===n&&(c.href=d+"/css/"+o,c.rel="stylesheet");}'
    )
    js.write_text(source, encoding="utf-8")

    def _fail_fetch(*_args, **_kwargs):
        raise AssertionError("dynamic runtime base must not be downloaded")

    monkeypatch.setattr(downloader, "fetch_bytes", _fail_fetch)
    monkeypatch.setattr(cdn_localizer, "fetch_bytes", downloader.fetch_bytes)

    result = cdn_localizer.localize_cdn_urls(tmp_path)

    assert result.files_updated == 0
    assert js.read_text(encoding="utf-8") == source


def test_downloads_zero_form_runtime_dependencies(tmp_path: Path, monkeypatch) -> None:
    """Zero-block forms need CSS/JS that aida-zero-forms loads dynamically."""
    page = tmp_path / "index.html"
    page.write_text(
        '<html><body><div class="tn-atom__form"></div></body></html>',
        encoding="utf-8",
    )

    fetched_urls: list[str] = []

    def _fetch(url: str, **_kw):
        fetched_urls.append(url)
        return (f"/* {url} */".encode("utf-8"), False)

    monkeypatch.setattr(downloader, "fetch_bytes", _fetch)
    monkeypatch.setattr(cdn_localizer, "fetch_bytes", downloader.fetch_bytes)

    result = cdn_localizer.localize_cdn_urls(tmp_path)

    assert result.download_failures == 0
    assert result.urls_localized >= 4
    assert (tmp_path / "css" / "aida-zero-form-horizontal.min.css").is_file()
    assert (tmp_path / "css" / "aida-zero-form-errorbox.min.css").is_file()
    assert (tmp_path / "js" / "aida-forms-1.0.min.js").is_file()
    assert (tmp_path / "js" / "aida-fallback-1.0.min.js").is_file()
    assert "https://static.tildacdn.com/css/aida-zero-form-horizontal.min.css" in fetched_urls


def test_uses_bundled_zero_form_dependencies_when_cdn_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Bundled CSS/fallback keeps zero forms usable in offline processing."""
    import urllib.error

    page = tmp_path / "index.html"
    page.write_text(
        '<html><body><div class="tn-atom__form"></div></body></html>',
        encoding="utf-8",
    )
    (tmp_path / "js").mkdir()
    (tmp_path / "js" / "aida-forms-1.0.min.js").write_text("forms", encoding="utf-8")

    def _fail(*_args, **_kw):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(downloader, "fetch_bytes", _fail)
    monkeypatch.setattr(cdn_localizer, "fetch_bytes", downloader.fetch_bytes)

    result = cdn_localizer.localize_cdn_urls(tmp_path)

    assert (tmp_path / "css" / "aida-zero-form-horizontal.min.css").is_file()
    assert (tmp_path / "css" / "aida-zero-form-errorbox.min.css").is_file()
    assert (tmp_path / "js" / "aida-fallback-1.0.min.js").is_file()
    assert result.download_failures == 0


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

    result = cdn_localizer.localize_cdn_urls(tmp_path)

    # Один URL → одна попытка с aida path → одна с reverse path = 2 запроса всего
    # А не 4 (двойное обращение от двух файлов)
    assert call_count["n"] <= 2, f"Слишком много повторных попыток: {call_count['n']}"
    assert result.download_failures == 1
    assert result.failed_urls == ["https://static.tildacdn.com/missing/x.png"]


def test_uses_browser_like_user_agent_for_cdn_downloads(tmp_path: Path, monkeypatch) -> None:
    js = tmp_path / "test.js"
    js.write_text('var u = "https://static.tildacdn.com/js/tilda-extra.js";', encoding="utf-8")

    seen_user_agents: list[str] = []

    def _fetch(_url, **kw):
        seen_user_agents.append(kw.get("user_agent", ""))
        return (b"js", False)

    monkeypatch.setattr(downloader, "fetch_bytes", _fetch)
    monkeypatch.setattr(cdn_localizer, "fetch_bytes", downloader.fetch_bytes)

    cdn_localizer.localize_cdn_urls(tmp_path)

    assert seen_user_agents
    assert "Mozilla/5.0" in seen_user_agents[0]


def test_does_not_overwrite_existing_local_file(tmp_path: Path, monkeypatch) -> None:
    """Если файл уже существует локально — cdn_localizer его не должен скачивать.

    Иначе перезатирается обработанная refs.py версия (с til→ai в селекторах)
    свежей оригинальной с CDN, и querySelector в JS перестаёт находить
    переименованные CSS-классы.
    """
    # Локальный JS уже существует с обработанным содержимым
    js = tmp_path / "js" / "phone-mask.js"
    js.parent.mkdir()
    js.write_text(
        'var sel = "https://static.tildacdn.com/lib/x.png"; var c = ".ai-input-rec";',
        encoding="utf-8",
    )

    fetched_urls: list[str] = []
    def _fetch(url, **_kw):
        fetched_urls.append(url)
        return (b"new-content-from-cdn", False)

    monkeypatch.setattr(downloader, "fetch_bytes", _fetch)
    monkeypatch.setattr(cdn_localizer, "fetch_bytes", downloader.fetch_bytes)

    cdn_localizer.localize_cdn_urls(tmp_path)

    # Файл скачался для нового пути lib/x.png (его не было)
    assert (tmp_path / "lib" / "x.png").exists()
    # Но JS-файл НЕ перезаписан (наша обработанная версия сохранена)
    text = js.read_text(encoding="utf-8")
    assert ".ai-input-rec" in text
    # URL внутри JS обновлён на относительный путь
    assert "tildacdn.com" not in text


def test_concat_url_handles_double_quote_inside_single_quote_string(tmp_path: Path, monkeypatch) -> None:
    """JS-литерал с double-quotes внутри single-quotes должен корректно обрабатываться.

    Real-world Tilda phone-mask содержит:
      'background-image:url(https://static.tildacdn.' + zone() + '/lib/flags/flags7.png);background-repeat:no-repeat;...flag="np"]{...}'
    Внутри одинарной строки есть "np" (двойные кавычки). Регекс не должен
    захватить эту "np" как закрывающую кавычку второй строки —
    он должен дойти до настоящей закрывающей одинарной кавычки.
    """
    js = tmp_path / "phone-mask.js"
    # Симулируем minified Tilda JS structure
    js.write_text(
        "var s = 'background-image:url(https://static.tildacdn.\" + zone() + \"/lib/flags/flags7.png);"
        'background-repeat:no-repeat}.t-flag[data-phonemask-flag=\"np\"]{width:16}\';\n'
        "var t = {ad: '-5px'};",
        encoding="utf-8",
    )

    monkeypatch.setattr(downloader, "fetch_bytes", lambda _url, **_kw: (b"png", False))
    monkeypatch.setattr(cdn_localizer, "fetch_bytes", downloader.fetch_bytes)

    cdn_localizer.localize_cdn_urls(tmp_path)

    text = js.read_text(encoding="utf-8")
    # tildacdn URL заменён на относительный
    assert "tildacdn.com" not in text
    assert "lib/flags/flags7.png" in text
    # `data-phonemask-flag="np"` СОХРАНЁН — это часть JS-строки
    assert 'data-phonemask-flag="np"' in text
    # Кавычки сбалансированы: количество ' и " не меньше чем должно быть
    assert text.count("'") >= 4  # var s='...';var t={ad:'-5px'};
    # JS должен быть syntactically valid (нет orphan кавычек)
    # Проверяем что после замены второй var не пострадал
    assert "var t = {ad: '-5px'};" in text


def test_concat_url_with_mixed_quote_types_preserves_balance(tmp_path: Path, monkeypatch) -> None:
    """Реальный кейс tilda-phone-mask: q1 и q2 РАЗНЫХ типов.

    JS:  ".css...background-image:url(https://static.tildacdn." + zone() + "/path...flag=\"np\"]...}"
    где первая строка открыта `"`, закрыта `"` (q1=`"`), а вторая строка
    открыта `'` и закрыта `'` (q2=`'`).

    Если replacement отбрасывает q1 — открывающая `"` слева остаётся
    без пары и Node.js падает с `Unexpected identifier 'np'`.

    Корректное поведение: replacement сохраняет q1, добавляет `+` и
    эмитит новый литерал q2 path suffix q2.
    """
    js = tmp_path / "phone-mask.js"
    # Минимизированный кусок реального Tilda JS — q1=", q2='
    js.write_text(
        'var css = ".t-input{padding:0}.t-phone-mask__flag{background-image:'
        'url(https://static.tildacdn." + t_zone() + '
        "'/lib/flags/flags7.png);background-repeat:no-repeat}"
        '.t-phone-mask__flag[data-phonemask-flag=\"np\"]{width:16px}\';\n'
        'var palette = {ad:"-5px"};',
        encoding="utf-8",
    )
    monkeypatch.setattr(downloader, "fetch_bytes", lambda _url, **_kw: (b"png", False))
    monkeypatch.setattr(cdn_localizer, "fetch_bytes", downloader.fetch_bytes)

    cdn_localizer.localize_cdn_urls(tmp_path)

    text = js.read_text(encoding="utf-8")
    # URL заменён на локальный путь
    assert "tildacdn." not in text
    assert "lib/flags/flags7.png" in text
    # q1 (закрывающая `"` первой строки) сохранена — кавычки сбалансированы
    # Подсчёт unescaped кавычек: должно быть чётное число каждого типа
    unescaped_dq = sum(1 for i, c in enumerate(text) if c == '"' and (i == 0 or text[i-1] != '\\'))
    unescaped_sq = sum(1 for i, c in enumerate(text) if c == "'" and (i == 0 or text[i-1] != '\\'))
    assert unescaped_dq % 2 == 0, f"unbalanced double quotes: {unescaped_dq}"
    assert unescaped_sq % 2 == 0, f"unbalanced single quotes: {unescaped_sq}"
    # Хвост файла не пострадал
    assert 'var palette = {ad:"-5px"};' in text
