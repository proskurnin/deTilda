from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.images import fix_project_images


def test_fix_project_images_promotes_full_sources(tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text(
        '<img class="t-img" src="images/preview.jpg" data-original="images/full.jpg" data-lazy="images/preview.jpg">\n'
        '<div class="t-bgimg" style="background-image:url(\'images/preview-bg.jpg\');" '
        'data-original="images/full-bg.jpg"></div>',
        encoding="utf-8",
    )

    result = fix_project_images(tmp_path)
    text = html.read_text(encoding="utf-8")

    assert result.updated_files == 1
    assert result.img_tags_fixed >= 1
    assert result.background_tags_fixed >= 1
    assert 'src="images/full.jpg"' in text
    assert 'data-lazy="images/full.jpg"' in text
    assert 'background-image:url("images/full-bg.jpg")' in text


def test_fix_project_images_counts_unresolved_candidates(tmp_path: Path) -> None:
    html = tmp_path / "page.html"
    html.write_text(
        '<img src="images/preview.jpg" data-original="images/full.jpg">',
        encoding="utf-8",
    )

    result = fix_project_images(tmp_path)

    assert result.updated_files == 1
    assert result.unresolved_candidates == 0
    assert 'src="images/full.jpg"' in html.read_text(encoding="utf-8")
