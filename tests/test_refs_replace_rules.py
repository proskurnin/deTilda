from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

yaml_stub = sys.modules.get("yaml")
if yaml_stub is None:
    yaml_stub = types.ModuleType("yaml")
    sys.modules["yaml"] = yaml_stub

def _fake_safe_load(_text: str, *_args, **_kwargs):
    return {
        "patterns": {
            "replace_rules": [
                {"pattern": r"(?i)\bt-", "replacement": "ai-"},
                {"pattern": r"(?i)\btil", "replacement": "ai"},
            ],
            "ignore_prefixes": ["http://", "https://", "//", "data:", "mailto:", "tel:", "#"],
            "text_extensions": [".html"],
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


def test_replace_rules_patch_html(tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text(
        '<div class="t-rec t-records">\n'
        '  <img src="https://static.tildacdn.com/path/img.png" />\n'
        '</div>',
        encoding="utf-8",
    )

    loader = ConfigLoader(ROOT)
    assert loader.patterns()["replace_rules"], "replace_rules should be loaded from stub"
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
    assert loader.patterns()["replace_rules"], "replace_rules should be loaded from stub"
    update_all_refs_in_project(tmp_path, {}, loader)

    result = page.read_text(encoding="utf-8")
    assert "ai-rec" in result
    assert "forms.aidacdn.com" in result

    other = tmp_path / "second.html"
    other.write_text('<div class="t-rec"></div>', encoding="utf-8")

    update_all_refs_in_project(tmp_path, {})

    assert "ai-rec" in other.read_text(encoding="utf-8")
