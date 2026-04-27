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
from core.schemas import PatternsConfig, ServiceFilesConfig


def _make_configs() -> tuple[PatternsConfig, ServiceFilesConfig]:
    patterns_cfg = PatternsConfig.model_validate({"text_extensions": [".html"]})
    service_cfg = ServiceFilesConfig.model_validate({
        "pipeline_stages": {
            "normalize_case": {
                "enabled": True,
                "extensions": [".html"],
            }
        }
    })
    return patterns_cfg, service_cfg


def test_case_normalization_updates_relative_links(tmp_path: Path) -> None:
    project_root = tmp_path
    rename_map: dict[str, str] = {}
    stats = AssetStats()
    patterns_cfg, service_cfg = _make_configs()

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
    # На case-insensitive ФС (macOS) Job.HTML.exists() вернёт True для job.html —
    # проверяем реальное имя файла через iterdir
    actual_files = {p.name for p in project_root.iterdir() if p.is_file()}
    assert "job.html" in actual_files
    assert "Job.HTML" not in actual_files

    main_text = (project_root / "main.html").read_text(encoding="utf-8")
    assert "./job.html" in main_text
    assert "/job.html" in main_text
    assert "/job" in main_text

    nested_text = (pages_dir / "index.html").read_text(encoding="utf-8")
    assert "../job.html" in nested_text
    assert "..\\job.html" in nested_text

    assert rename_map["Job.HTML"] == "job.html"


def test_case_normalization_lowercases_links_without_matching_files(tmp_path: Path) -> None:
    project_root = tmp_path
    rename_map: dict[str, str] = {}
    stats = AssetStats()
    patterns_cfg, service_cfg = _make_configs()

    (project_root / "main.html").write_text(
        '<a href="/Job"></a><a href="./Sub/Job"></a><a href="..\\Job"></a>',
        encoding="utf-8",
    )

    _apply_case_normalization(project_root, rename_map, stats, patterns_cfg, service_cfg)

    main_text = (project_root / "main.html").read_text(encoding="utf-8")
    assert '/job' in main_text
    assert './sub/job' in main_text
    assert '..\\job' in main_text
    assert stats.renamed == 0
    assert rename_map == {}


def test_case_normalization_does_not_break_js_identifiers(tmp_path: Path) -> None:
    """JS identifiers вроде /sizerWidth не должны lowercased в _apply_case_normalization.

    Регекс _RELATIVE_LINK_LOWERCASE_PATTERN matches `/sizerWidth` как path,
    но в JS это не путь к файлу, а математическое выражение или часть
    base64-строки. Lowercasing ломает minified JS.
    """
    project_root = tmp_path
    rename_map: dict[str, str] = {}
    stats = AssetStats()
    patterns_cfg, service_cfg = _make_configs()

    # JS файл — должен остаться нетронутым
    (project_root / "code.js").write_text(
        "var x = colAmount/sizerWidth + 1;\n"
        "var img = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';",
        encoding="utf-8",
    )
    # Тестовый patterns_cfg включает только .html — добавим .js
    patterns_cfg = PatternsConfig.model_validate({"text_extensions": [".html", ".js"]})

    _apply_case_normalization(project_root, rename_map, stats, patterns_cfg, service_cfg)

    js_text = (project_root / "code.js").read_text(encoding="utf-8")
    # JS identifiers сохранены
    assert "sizerWidth" in js_text
    # base64 payload сохранён
    assert "yH5BAEAAAA" in js_text
