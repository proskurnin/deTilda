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
            "htaccess_patterns": {
                "rewrite_rule": r"(?im)^[ \t]*RewriteRule[ \t]+\^/?([a-z0-9\-_/]+)\??\$?[ \t]+([^ \t]+)",
                "redirect": r"(?im)^[ \t]*Redirect(?:Permanent|[ \t]+3\d{2})?[ \t]+(/[^ \t]+)[ \t]+([^ \t]+)",
                "soft_fallback_to_404": False,
                "auto_stub_missing_routes": False,
                "fallback_target": "404.html",
            },
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
                '<a href="#popup:myform">Popup</a>',
                '<div data-href="#rec568425147"></div>',
                '<img src="#rec568425147" />',
                '<a href="/#rec570511988">Menu1</a>',
                '<a href="/#rec568425147">Menu2</a>',
                '<a href="/#rec769311166">Menu3</a>',
                '<a href="/#rec568506512">Menu4</a>',
                '<a href="/#rec568536244">Menu5</a>',
                '<a href="/#contacts">MenuContacts</a>',
                '<a href="page35179958.html#rec568425147">PageAnchor</a>',
                '<a href="https://example.com/#x">ExternalAnchor</a>',
                '<a href="about.html">About</a>',
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / ".htaccess").write_text("DirectoryIndex index.html\n", encoding="utf-8")
    (tmp_path / "page35179958.html").write_text("<html></html>", encoding="utf-8")

    loader = ConfigLoader(ROOT)
    update_all_refs_in_project(tmp_path, {"about.html": "about-us.html"}, loader)

    content = html.read_text(encoding="utf-8")

    assert 'href="#rec568425147"' in content
    assert 'href="#section"' in content
    assert 'href="#contacts"' in content
    assert 'href="#form"' in content
    assert 'href="#popup:myform"' in content
    assert 'data-href="#rec568425147"' in content
    assert 'src="#rec568425147"' in content
    assert 'href="#rec570511988"' in content
    assert 'href="#rec568425147"' in content
    assert 'href="#rec769311166"' in content
    assert 'href="#rec568506512"' in content
    assert 'href="#rec568536244"' in content
    assert 'href="#contacts"' in content
    assert '/#rec' not in content
    assert 'href="page35179958.html#rec568425147"' in content
    assert 'href="https://example.com/#x"' in content
    assert 'href="file:///#rec568425147"' not in content
    assert 'href="file:///' not in content
    assert 'href="about-us.html"' in content


def test_same_page_root_anchor_is_rewritten_for_reused_header_fragment(tmp_path: Path) -> None:
    (tmp_path / ".htaccess").write_text("DirectoryIndex page35179958.html\n", encoding="utf-8")
    (tmp_path / "page35179958.html").write_text("<html></html>", encoding="utf-8")
    body = tmp_path / "files" / "page35179958body.html"
    body.parent.mkdir(parents=True, exist_ok=True)
    body.write_text('<a href="/#rec568536244">Как добраться</a>', encoding="utf-8")

    loader = ConfigLoader(ROOT)
    update_all_refs_in_project(tmp_path, {}, loader)

    content = body.read_text(encoding="utf-8")
    assert 'href="#rec568536244"' in content
    assert 'href="page35179958.html#rec568536244"' not in content


def test_cross_page_route_is_preserved(tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text('<a href="/blog">Blog</a>', encoding="utf-8")
    (tmp_path / ".htaccess").write_text("DirectoryIndex index.html\n", encoding="utf-8")
    (tmp_path / "blog.html").write_text("<html>blog</html>", encoding="utf-8")

    loader = ConfigLoader(ROOT)
    update_all_refs_in_project(tmp_path, {}, loader)

    assert 'href="/blog"' in html.read_text(encoding="utf-8")


def test_mixed_menu_with_anchors_and_routes_processed_correctly(tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text(
        '<a href="/#rec570511988">Цены</a>'
        '<a href="/rooms">Rooms</a>'
        '<a href="/#rec568425147">Об отеле</a>'
        '<a href="/itcamp">ITCamp</a>',
        encoding="utf-8",
    )
    (tmp_path / ".htaccess").write_text("DirectoryIndex index.html\n", encoding="utf-8")
    (tmp_path / "rooms.html").write_text("<html>rooms</html>", encoding="utf-8")
    (tmp_path / "itcamp.html").write_text("<html>itcamp</html>", encoding="utf-8")

    loader = ConfigLoader(ROOT)
    update_all_refs_in_project(tmp_path, {}, loader)

    content = html.read_text(encoding="utf-8")
    assert 'href="#rec570511988"' in content
    assert 'href="#rec568425147"' in content
    assert 'href="/rooms"' in content
    assert 'href="/itcamp"' in content


def test_root_anchor_on_non_root_page_is_not_rewritten(tmp_path: Path) -> None:
    (tmp_path / ".htaccess").write_text("DirectoryIndex index.html\n", encoding="utf-8")
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    html = tmp_path / "blog.html"
    html.write_text('<a href="/#rec570511988">To homepage block</a>', encoding="utf-8")

    loader = ConfigLoader(ROOT)
    update_all_refs_in_project(tmp_path, {}, loader)

    assert 'href="/#rec570511988"' in html.read_text(encoding="utf-8")


def test_local_preview_menu_anchor_stays_document_local(tmp_path: Path) -> None:
    (tmp_path / ".htaccess").write_text("DirectoryIndex page35179958.html\n", encoding="utf-8")
    html = tmp_path / "page35179958.html"
    html.write_text('<a href="/#rec568536244">Как добраться</a>', encoding="utf-8")

    loader = ConfigLoader(ROOT)
    update_all_refs_in_project(tmp_path, {}, loader)

    content = html.read_text(encoding="utf-8")
    assert 'href="#rec568536244"' in content
    assert "file:///#" not in content
