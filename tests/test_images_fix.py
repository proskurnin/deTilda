from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.images import fix_project_images


def test_fix_project_images_promotes_only_placeholder_img_sources(tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text(
        '<img class="t-img" src="images/1px.png" data-original="images/full.jpg" data-lazy="images/preview.jpg">\n'
        '<div class="t-bgimg" style="background-image:url("images/test.jpg"); background-size:cover;"></div>',
        encoding="utf-8",
    )
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "full.jpg").write_bytes(b"x")

    result = fix_project_images(tmp_path)
    text = html.read_text(encoding="utf-8")

    assert result.updated_files == 1
    assert result.img_tags_fixed >= 1
    assert result.background_tags_fixed >= 1
    assert 'src="images/full.jpg"' in text
    assert 'data-lazy="images/preview.jpg"' in text
    assert "background-image:url('images/test.jpg')" in text


def test_fix_project_images_skips_missing_full_image_candidates(tmp_path: Path) -> None:
    html = tmp_path / "page.html"
    html.write_text(
        '<img src="images/1x1.gif" data-original="images/full.jpg">',
        encoding="utf-8",
    )

    result = fix_project_images(tmp_path)

    assert result.updated_files == 0
    assert result.unresolved_candidates == 1
    assert 'src="images/1x1.gif"' in html.read_text(encoding="utf-8")


def test_fix_project_images_does_not_override_existing_img_src(tmp_path: Path) -> None:
    html = tmp_path / "fixture.html"
    html.write_text(
        '<img class="t-img" src="images/preview.jpg" data-original="images/full.jpg" data-img-zoom-url="images/zoom.jpg">\n'
        '<img class="t-img2" src="images/photo_-_empty_1.jpeg" data-original="images/real.jpeg" data-lazy-rule="skip">\n'
        '<div class="t-cover__carrier" style="background:url("images/bg.jpg") center center / cover;"></div>\n',
        encoding="utf-8",
    )
    (tmp_path / "images").mkdir()
    for name in ("full.jpg", "zoom.jpg", "real.jpeg"):
        (tmp_path / "images" / name).write_bytes(b"x")

    fix_project_images(tmp_path)
    text = html.read_text(encoding="utf-8")

    assert 'src="images/preview.jpg"' in text
    assert 'data-original="images/full.jpg"' in text
    assert 'data-img-zoom-url="images/zoom.jpg"' in text
    assert 'src="images/real.jpeg"' in text
    assert "background:url('images/bg.jpg')" in text


def test_fix_project_images_keeps_normal_src_without_data_original(tmp_path: Path) -> None:
    html = tmp_path / "body.html"
    html.write_text('<img src="images/normal.jpg">', encoding="utf-8")
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "normal.jpg").write_bytes(b"x")

    result = fix_project_images(tmp_path)

    assert result.updated_files == 0
    assert result.img_tags_fixed == 0
    assert 'src="images/normal.jpg"' in html.read_text(encoding="utf-8")
