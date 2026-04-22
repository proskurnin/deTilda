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

from core.script_cleaner import remove_disallowed_scripts


class _FakeLoader:
    config_path = Path("tests/fake-config.yaml")

    def patterns(self) -> dict[str, object]:
        return {"text_extensions": [".html"]}

    def service_files(self) -> dict[str, object]:
        return {
            "scripts_to_remove_from_project": {
                "filenames": [
                    "tilda-stat-1.0.min.js",
                    "tilda-forms-1.0.min.js",
                    "tilda-events-1.0.min.js",
                    "tilda-fallback-1.0.min.js",
                ]
            }
        }


def test_script_cleaner_keeps_tilda_media_runtime_for_youtube(tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text(
        """
        <div class="t-video-lazyload" data-youtube-url="https://www.youtube.com/watch?v=abc"></div>
        <script src="js/tilda-events-1.0.min.js"></script>
        <script src="js/tilda-fallback-1.0.min.js"></script>
        <script src="js/tilda-forms-1.0.min.js"></script>
        <script src="js/tilda-stat-1.0.min.js"></script>
        """,
        encoding="utf-8",
    )

    loader = _FakeLoader()
    removed = remove_disallowed_scripts(tmp_path, loader)
    text = html.read_text(encoding="utf-8")

    assert removed == 2
    assert "tilda-events-1.0.min.js" in text
    assert "tilda-fallback-1.0.min.js" in text
    assert "tilda-forms-1.0.min.js" not in text
    assert "tilda-stat-1.0.min.js" not in text


def test_script_cleaner_removes_all_configured_scripts_without_media_markers(tmp_path: Path) -> None:
    html = tmp_path / "plain.html"
    html.write_text(
        """
        <div>Plain page without media blocks</div>
        <script src="js/tilda-events-1.0.min.js"></script>
        <script src="js/tilda-fallback-1.0.min.js"></script>
        <script src="js/tilda-forms-1.0.min.js"></script>
        <script src="js/tilda-stat-1.0.min.js"></script>
        """,
        encoding="utf-8",
    )

    loader = _FakeLoader()
    removed = remove_disallowed_scripts(tmp_path, loader)
    text = html.read_text(encoding="utf-8")

    assert removed == 4
    assert "tilda-events-1.0.min.js" not in text
    assert "tilda-fallback-1.0.min.js" not in text
