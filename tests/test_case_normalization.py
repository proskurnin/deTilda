from __future__ import annotations

from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "yaml" not in sys.modules:
    yaml_stub = types.ModuleType("yaml")
    yaml_stub.safe_load = lambda *_args, **_kwargs: {}
    sys.modules["yaml"] = yaml_stub

from core.assets import AssetStats, _apply_case_normalization


def test_case_normalization_updates_relative_links(tmp_path: Path) -> None:
    project_root = tmp_path
    rename_map: dict[str, str] = {}
    stats = AssetStats()
    patterns_cfg = {"text_extensions": [".html"]}
    service_cfg = {
        "pipeline_stages": {
            "normalize_case": {
                "enabled": True,
                "extensions": [".html"],
            }
        }
    }

    (project_root / "Job.HTML").write_text("content", encoding="utf-8")
    (project_root / "main.html").write_text(
        '<a href="./Job.HTML"></a><a href="/Job.HTML"></a><a href="/Job"></a>',
        encoding="utf-8",
    )

    pages_dir = project_root / "pages"
    pages_dir.mkdir()
    (pages_dir / "index.html").write_text(
        '<a href="../Job.HTML"></a><img src="..\\Job.HTML" />',
        encoding="utf-8",
    )

    _apply_case_normalization(project_root, rename_map, stats, patterns_cfg, service_cfg)

    assert stats.renamed == 1
    assert not (project_root / "Job.HTML").exists()
    assert (project_root / "job.html").exists()

    main_text = (project_root / "main.html").read_text(encoding="utf-8")
    assert "./job.html" in main_text
    assert "/job.html" in main_text
    assert "/job" in main_text

    nested_text = (pages_dir / "index.html").read_text(encoding="utf-8")
    assert "../job.html" in nested_text
    assert "..\\job.html" in nested_text

    assert rename_map["Job.HTML"] == "job.html"
