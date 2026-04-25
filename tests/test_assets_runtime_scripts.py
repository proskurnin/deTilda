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

from core.assets import rename_and_cleanup_assets
from core.schemas import ImagesConfig, PatternsConfig, ServiceFilesConfig


class _FakeLoader:
    base_dir = ROOT

    def patterns(self) -> PatternsConfig:
        return PatternsConfig.model_validate({
            "assets": {"til_to_ai_filename": r"\btil"},
            "text_extensions": [".html"],
        })

    def images(self) -> ImagesConfig:
        return ImagesConfig.model_validate({
            "delete_physical_files": {"as_is": []},
        })

    def service_files(self) -> ServiceFilesConfig:
        return ServiceFilesConfig.model_validate({
            "scripts_to_delete": {
                "files": [
                    "aida-stat-1.0.min.js",
                    "aida-forms-1.0.min.js",
                    "aida-fallback-1.0.min.js",
                    "aida-events-1.0.min.js",
                ]
            },
            "rename_map_output": {"filename": "{project}_rename_map.json", "location": "logs"},
        })


def test_assets_keep_runtime_scripts_when_media_markers_exist(tmp_path: Path) -> None:
    (tmp_path / "js").mkdir()
    (tmp_path / "js" / "tilda-events-1.0.min.js").write_text("", encoding="utf-8")
    (tmp_path / "js" / "tilda-fallback-1.0.min.js").write_text("", encoding="utf-8")
    (tmp_path / "js" / "tilda-forms-1.0.min.js").write_text("", encoding="utf-8")
    (tmp_path / "js" / "tilda-stat-1.0.min.js").write_text("", encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<div class="t-gallery"></div><script src="js/aida-events-1.0.min.js"></script>',
        encoding="utf-8",
    )

    rename_and_cleanup_assets(tmp_path, loader=_FakeLoader())

    assert (tmp_path / "js" / "aida-events-1.0.min.js").exists()
    assert (tmp_path / "js" / "aida-fallback-1.0.min.js").exists()
    assert not (tmp_path / "js" / "aida-forms-1.0.min.js").exists()
    assert not (tmp_path / "js" / "aida-stat-1.0.min.js").exists()


def test_assets_remove_runtime_scripts_without_media_markers(tmp_path: Path) -> None:
    (tmp_path / "js").mkdir()
    (tmp_path / "js" / "tilda-events-1.0.min.js").write_text("", encoding="utf-8")
    (tmp_path / "js" / "tilda-fallback-1.0.min.js").write_text("", encoding="utf-8")
    (tmp_path / "index.html").write_text("<div>plain</div>", encoding="utf-8")

    rename_and_cleanup_assets(tmp_path, loader=_FakeLoader())

    assert not (tmp_path / "js" / "aida-events-1.0.min.js").exists()
    assert not (tmp_path / "js" / "aida-fallback-1.0.min.js").exists()
