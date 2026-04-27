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
from core.schemas import PatternsConfig, ServiceFilesConfig


class _FakeLoader:
    config_path = Path("tests/fake-config.yaml")

    def patterns(self) -> PatternsConfig:
        return PatternsConfig.model_validate({"text_extensions": [".html"]})

    def service_files(self) -> ServiceFilesConfig:
        return ServiceFilesConfig.model_validate({
            "scripts_to_remove_from_project": {
                "filenames": [
                    "tilda-stat-1.0.min.js",
                    "tilda-forms-1.0.min.js",
                    "tilda-events-1.0.min.js",
                    "tilda-fallback-1.0.min.js",
                    "aida-stat-1.0.min.js",
                ]
            }
        })


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


def test_removes_inline_script_referencing_deleted_file(tmp_path: Path) -> None:
    """Inline <script> с динамической загрузкой удалённого файла должен удаляться.

    Tilda кладёт аналитику через setTimeout(...) который создаёт <script src="js/aida-stat.js">.
    Сам файл мы удалили в assets, но inline-загрузчик остался → 404 в браузере.
    """
    html = tmp_path / "page.html"
    html.write_text(
        '<html><body>\n'
        '<script type="text/javascript">'
        "setTimeout(function(){var s=document.createElement('script');"
        "s.src='js/aida-stat-1.0.min.js';document.body.appendChild(s);},2000);"
        "</script>\n"
        '<script src="js/normal.js"></script>\n'
        '</body></html>',
        encoding="utf-8",
    )

    loader = _FakeLoader()
    removed = remove_disallowed_scripts(tmp_path, loader)
    text = html.read_text(encoding="utf-8")
    # Inline-скрипт с aida-stat удалён
    assert "aida-stat" not in text
    # Обычный скрипт не тронут
    assert "normal.js" in text
    assert removed >= 1
