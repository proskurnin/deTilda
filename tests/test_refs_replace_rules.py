from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Сначала пробуем настоящий PyYAML — если установлен, оригинальный safe_load
# нужен тестам, которые проверяют production-конфиг (а не моки).
try:
    import yaml as _real_yaml  # noqa: F401
    _real_yaml_safe_load = _real_yaml.safe_load
    yaml_stub = _real_yaml
except ImportError:
    yaml_stub = types.ModuleType("yaml")
    sys.modules["yaml"] = yaml_stub
    _real_yaml_safe_load = None


def _fake_safe_load(_text: str, *_args, **_kwargs):
    return {
        "patterns": {
            "replace_rules": [
                {"pattern": r"(?i)\bt-", "replacement": "ai-"},
                {"pattern": r"(?i)\btil", "replacement": "ai"},
            ],
            "ignore_prefixes": ["http://", "https://", "//", "data:", "mailto:", "tel:", "#"],
            "text_extensions": [".html", ".js"],
        },
        "images": {
            "comment_out_link_tags": {"rel_values": []},
            "replace_links_with_1px": {"patterns": []},
            "comment_out_links": {"patterns": []},
        },
        "service_files": {},
    }

yaml_stub.safe_load = _fake_safe_load

from core.config_loader import ConfigLoader
from core.refs import update_all_refs_in_project


def test_msapplication_tile_meta_tags_not_renamed(tmp_path: Path) -> None:
    """msapplication-TileColor/TileImage — стандарт Microsoft, til→ai ломает.

    Без защиты `\\btil` matches `Til` в `TileColor` (после `-` граница слова),
    и метатеги превращаются в `msapplication-aieColor`/`msapplication-aieImage`,
    которые Edge/IE не понимают. Lookahead в config.yaml должен это
    предотвращать.
    """
    import pytest
    if _real_yaml_safe_load is None or _real_yaml_safe_load is _fake_safe_load:
        pytest.skip("Тест требует настоящий PyYAML для чтения production-конфига")

    page = tmp_path / "index.html"
    page.write_text(
        '<head>'
        '<meta name="msapplication-TileColor" content="#ffffff">'
        '<meta name="msapplication-TileImage" content="images/tild-favicon.png">'
        '<div class="t-rec">tilda</div>'
        '</head>',
        encoding="utf-8",
    )

    yaml_stub.safe_load = _real_yaml_safe_load
    try:
        # ConfigLoader кэширует AppConfig — для production-конфига нужен новый loader
        loader = ConfigLoader(ROOT)
        update_all_refs_in_project(tmp_path, {}, loader)
    finally:
        yaml_stub.safe_load = _fake_safe_load

    text = page.read_text(encoding="utf-8")
    # Microsoft-стандарт нетронут
    assert 'msapplication-TileColor' in text
    assert 'msapplication-TileImage' in text
    assert 'msapplication-aie' not in text
    # Tilda-токены переименованы как обычно
    assert '"ai-rec"' in text
    assert 'aida' in text  # tilda → aida


def test_replace_rules_patch_html(tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text(
        '<div class="t-rec t-records">\n'
        '  <img src="https://static.tildacdn.com/path/img.png" />\n'
        '</div>',
        encoding="utf-8",
    )

    loader = ConfigLoader(ROOT)
    assert loader.patterns().replace_rules, "replace_rules should be loaded from stub"
    update_all_refs_in_project(tmp_path, {}, loader)

    content = html.read_text(encoding="utf-8")
    assert "ai-rec" in content
    assert "ai-records" in content
    assert "static.aidacdn.com" in content


def test_replace_rules_without_explicit_loader(tmp_path: Path) -> None:
    page = tmp_path / "page.html"
    page.write_text(
        '<span class="t-rec">https://forms.tildacdn.com/form.js</span>',
        encoding="utf-8",
    )

    loader = ConfigLoader(ROOT)
    assert loader.patterns().replace_rules, "replace_rules should be loaded from stub"
    update_all_refs_in_project(tmp_path, {}, loader)

    result = page.read_text(encoding="utf-8")
    assert "ai-rec" in result
    assert "forms.aidacdn.com" in result

    other = tmp_path / "second.html"
    other.write_text('<div class="t-rec"></div>', encoding="utf-8")

    update_all_refs_in_project(tmp_path, {})

    assert "ai-rec" in other.read_text(encoding="utf-8")


def test_js_replace_rules_keep_camel_case_and_regex_literals(tmp_path: Path) -> None:
    script = tmp_path / "aida-blocks-1.min.js"
    script.write_text(
        "\n".join(
            [
                "const width = newImage.naturalWidth + sizerWidth + colAmount;",
                "const re = /OS \\d/;",
                "const selector = '.t-records .t-popup';",
                "const attr = 'data-tilda-mode';",
                "const eventName = 'tildamodal:show';",
                "window.Tilda.sendEventToStatistics();",
                "Tilda.sendEventToStatistics();",
            ]
        ),
        encoding="utf-8",
    )

    loader = ConfigLoader(ROOT)
    update_all_refs_in_project(tmp_path, {}, loader)

    result = script.read_text(encoding="utf-8")
    assert "newImage.naturalWidth" in result
    assert "sizerWidth" in result
    assert "colAmount" in result
    assert "/OS \\d/" in result
    assert ".ai-records .ai-popup" in result
    assert "data-aida-mode" in result
    assert "aidamodal:show" in result
    assert "window.aida.sendEventToStatistics()" in result
    assert "aida.sendEventToStatistics()" in result


def test_js_replace_does_not_break_arithmetic_identifiers(tmp_path: Path) -> None:
    """В minified JS выражения вроде (t-this._x) не должны трогаться til→ai.

    Регекс для строковых литералов в minified коде может ошибочно склеить
    разные литералы. Если внутри захваченного куска есть и CSS-класс
    (`'t-rec'`) и арифметика (`t-this._previousLoopTime`), наш replace
    \\bt- → ai- ломает identifier (`t-this` → `ai-this` → ReferenceError).
    """
    js = tmp_path / "lazy.min.js"
    # Симулируем minified код где между двумя литералами есть math expression
    js.write_text(
        'var x="t-rec";function f(t){return o-(t-this._previousLoopTime)}var y="t-popup"',
        encoding="utf-8",
    )

    loader = ConfigLoader(ROOT)
    update_all_refs_in_project(tmp_path, {}, loader)

    text = js.read_text(encoding="utf-8")
    # CSS-классы в строках переименованы (это правильно)
    assert '"ai-rec"' in text
    assert '"ai-popup"' in text
    # Identifier t-this НЕ тронут (после `(` это арифметика)
    assert "(t-this._previousLoopTime)" in text
    assert "ai-this" not in text


def test_js_replace_protects_base64_in_strings(tmp_path: Path) -> None:
    """base64 строки внутри JS-литералов не должны портиться til→ai.

    Если в литерале есть base64 с подстрокой til (например fragment '/yH5...'),
    наш replace может его повредить. Lookbehind защищает от ложных срабатываний.
    """
    js = tmp_path / "code.js"
    js.write_text(
        'var x="t-rec";var img="data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=";',
        encoding="utf-8",
    )

    loader = ConfigLoader(ROOT)
    update_all_refs_in_project(tmp_path, {}, loader)

    text = js.read_text(encoding="utf-8")
    # CSS класс заменён
    assert '"ai-rec"' in text
    # Base64 не должен потерять/исказить байты
    assert "R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=" in text


def test_js_regex_literal_with_quote_does_not_desync_string_scanner(tmp_path: Path) -> None:
    """Регексп-литерал с кавычкой внутри (`/"/gi`) не должен сбивать парность.

    Реальный кейс из lazyload-1.3.min.js: между двумя строковыми литералами
    есть `replace(/"/gi, "")` — кавычка внутри regex literal. Наивный
    rege-сканер строк видит её как opening quote и склеивает кусок кода
    с следующим литералом, в результате чего селектор `.t-cover__carrier`
    в самом конце файла остаётся непереименованным → ломается parallax.
    """
    js = tmp_path / "lazyload.min.js"
    js.write_text(
        'var s="t-rec";'
        'function clean(x){return x.replace(/"/gi,"")}'
        'var sel=".t-cover__carrier";'
        'var img=".t-img";',
        encoding="utf-8",
    )

    loader = ConfigLoader(ROOT)
    update_all_refs_in_project(tmp_path, {}, loader)

    text = js.read_text(encoding="utf-8")
    assert '"ai-rec"' in text
    assert '".ai-cover__carrier"' in text
    assert '".ai-img"' in text
    # Сам regex literal остался нетронутым
    assert "/\"/gi" in text
