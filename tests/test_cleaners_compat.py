from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
import types

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "yaml" not in sys.modules:
    yaml_stub = types.ModuleType("yaml")
    yaml_stub.safe_load = lambda *_args, **_kwargs: {}
    sys.modules["yaml"] = yaml_stub

from core.cleaners import clean_project_files
from core.schemas import PatternsConfig, ServiceFilesConfig


class _FakeLoader:
    def patterns(self) -> PatternsConfig:
        return PatternsConfig.model_validate({
            "robots_cleanup_patterns": [
                r"(?im)^\s*Disallow:\s*/tilda/(?:form).*\n?",
                r"(?im)^\s*Disallow:\s*/\*_escaped_fragment_\*/\s*\n?",
            ],
            "readme_cleanup_patterns": [
                {"pattern": r"(?im)^.*Published on Tilda\.cc.*\n?", "replacement": ""},
                {"pattern": r"(?i)\btilda\b", "replacement": "site"},
            ],
            "tilda_remnants_patterns": [r"(https?://|//)[^\s'\"]*tilda\.ws[^\s'\"]*"],
        })

    def service_files(self) -> ServiceFilesConfig:
        return ServiceFilesConfig.model_validate({
            "cleaner_options": {"files_to_clean_tilda_refs": ["robots.txt", "readme.txt"]}
        })


def test_clean_project_files_cleans_robots_and_readme(tmp_path: Path) -> None:
    (tmp_path / "robots.txt").write_text(
        "User-agent: *\nDisallow: /tilda/form\nDisallow: /*_escaped_fragment_*/\n",
        encoding="utf-8",
    )
    (tmp_path / "readme.txt").write_text(
        "Published on Tilda.cc\ncdn: https://example.tilda.ws/foo.js\nTILDA text\n",
        encoding="utf-8",
    )

    context = SimpleNamespace(project_root=tmp_path, config_loader=_FakeLoader())

    stats = clean_project_files(context, {})

    robots = (tmp_path / "robots.txt").read_text(encoding="utf-8")
    readme = (tmp_path / "readme.txt").read_text(encoding="utf-8")

    assert stats.updated == 2
    assert "Disallow: /tilda/form" not in robots
    assert "_escaped_fragment_" not in robots
    assert "Published on Tilda.cc" not in readme
    assert "tilda.ws" not in readme
    assert "site text" in readme
