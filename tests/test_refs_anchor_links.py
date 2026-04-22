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
            "replace_rules": [],
            # Deliberately no "#" prefix in ignore list to exercise explicit anchor bypass.
            "ignore_prefixes": ["http://", "https://", "//", "data:", "mailto:", "tel:"],
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


def test_anchor_links_are_not_rewritten_to_file_urls(tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text(
        "\n".join(
            [
                '<a href="#rec568425147">Block</a>',
                '<a href="#section">Section</a>',
                '<a href="#contacts">Contacts</a>',
                '<a href="#form">Form</a>',
                '<div data-href="#rec568425147"></div>',
                '<img src="#rec568425147" />',
                '<a href="about.html">About</a>',
            ]
        ),
        encoding="utf-8",
    )

    loader = ConfigLoader(ROOT)
    update_all_refs_in_project(tmp_path, {"about.html": "about-us.html"}, loader)

    content = html.read_text(encoding="utf-8")

    assert 'href="#rec568425147"' in content
    assert 'href="#section"' in content
    assert 'href="#contacts"' in content
    assert 'href="#form"' in content
    assert 'data-href="#rec568425147"' in content
    assert 'src="#rec568425147"' in content
    assert 'href="file:///#rec568425147"' not in content
    assert 'href="file:///' not in content
    assert 'href="about-us.html"' in content
