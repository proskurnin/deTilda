from pathlib import Path
import sys
import types
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

yaml_stub = sys.modules.get("yaml")
if yaml_stub is None:
    yaml_stub = types.ModuleType("yaml")
    yaml_stub.safe_load = lambda *_args, **_kwargs: {}
    sys.modules["yaml"] = yaml_stub

from core.htaccess import collect_routes
from core.schemas import PatternsConfig


class _Loader:
    def __init__(self, htaccess_patterns: dict) -> None:
        self._cfg = PatternsConfig.model_validate({"htaccess_patterns": htaccess_patterns})

    def patterns(self) -> PatternsConfig:
        return self._cfg


def test_collect_routes_soft_fallback_to_404(tmp_path: Path) -> None:
    (tmp_path / ".htaccess").write_text(
        "RewriteRule ^broken$ missing.html\n",
        encoding="utf-8",
    )
    (tmp_path / "404.html").write_text("<h1>404</h1>", encoding="utf-8")

    loader = _Loader({
        "rewrite_rule": r"(?im)^[ \t]*RewriteRule[ \t]+\^/?([a-z0-9\-_/]+)\??\$?[ \t]+([^ \t]+)",
        "redirect": r"(?im)^[ \t]*Redirect(?:Permanent|[ \t]+3\d{2})?[ \t]+(/[^ \t]+)[ \t]+([^ \t]+)",
        "soft_fallback_to_404": True,
        "fallback_target": "404.html",
    })
    result = collect_routes(tmp_path, loader)  # type: ignore[arg-type]

    assert result.routes["/broken"] == "404.html"
    info = result.get_route_info("/broken")
    assert info is not None
    assert info.exists
    assert info.target == "404.html"


def test_collect_routes_without_soft_fallback_keeps_broken_target(tmp_path: Path) -> None:
    (tmp_path / ".htaccess").write_text(
        "RewriteRule ^broken$ missing.html\n",
        encoding="utf-8",
    )

    loader = _Loader({
        "rewrite_rule": r"(?im)^[ \t]*RewriteRule[ \t]+\^/?([a-z0-9\-_/]+)\??\$?[ \t]+([^ \t]+)",
        "redirect": r"(?im)^[ \t]*Redirect(?:Permanent|[ \t]+3\d{2})?[ \t]+(/[^ \t]+)[ \t]+([^ \t]+)",
        "soft_fallback_to_404": False,
        "remove_unresolved_routes": False,
    })
    result = collect_routes(tmp_path, loader)  # type: ignore[arg-type]

    assert result.routes["/broken"] == "missing.html"
    info = result.get_route_info("/broken")
    assert info is not None
    assert not info.exists
    assert info.target == "missing.html"


def test_collect_routes_removes_legacy_broken_route_by_default(tmp_path: Path) -> None:
    htaccess_path = tmp_path / ".htaccess"
    htaccess_path.write_text(
        "RewriteRule ^legacy$ missing.html [L]\n",
        encoding="utf-8",
    )

    loader = _Loader({
        "rewrite_rule": r"(?im)^[ \t]*RewriteRule[ \t]+\^/?([a-z0-9\-_/]+)\??\$?[ \t]+([^ \t]+)",
        "redirect": r"(?im)^[ \t]*Redirect(?:Permanent|[ \t]+3\d{2})?[ \t]+(/[^ \t]+)[ \t]+([^ \t]+)",
        "soft_fallback_to_404": False,
    })
    result = collect_routes(tmp_path, loader)  # type: ignore[arg-type]

    assert "/legacy" not in result.routes
    assert "missing.html" not in htaccess_path.read_text(encoding="utf-8")
    assert len(result.missing_routes) == 1
    assert result.missing_routes[0].alias == "/legacy"
    assert result.missing_routes[0].action == "removed"


def test_collect_routes_auto_stub_creates_missing_file(tmp_path: Path) -> None:
    (tmp_path / ".htaccess").write_text(
        "RewriteRule ^broken$ missing.html\n",
        encoding="utf-8",
    )
    (tmp_path / "404.html").write_text("<h1>404</h1>", encoding="utf-8")

    loader = _Loader({
        "rewrite_rule": r"(?im)^[ \t]*RewriteRule[ \t]+\^/?([a-z0-9\-_/]+)\??\$?[ \t]+([^ \t]+)",
        "redirect": r"(?im)^[ \t]*Redirect(?:Permanent|[ \t]+3\d{2})?[ \t]+(/[^ \t]+)[ \t]+([^ \t]+)",
        "auto_stub_missing_routes": True,
        "fallback_target": "404.html",
    })
    result = collect_routes(tmp_path, loader)  # type: ignore[arg-type]

    assert result.routes["/broken"] == "missing.html"
    assert (tmp_path / "missing.html").exists()
    assert (tmp_path / "missing.html").read_text(encoding="utf-8") == "<h1>404</h1>"
    assert len(result.missing_routes) == 1
    assert result.missing_routes[0].alias == "/broken"
    assert result.missing_routes[0].action == "stub_created"


def test_collect_routes_counts_initial_and_autofixed_routes(tmp_path: Path) -> None:
    (tmp_path / ".htaccess").write_text(
        "RewriteRule ^broken$ missing.html\n",
        encoding="utf-8",
    )
    (tmp_path / "404.html").write_text("<h1>404</h1>", encoding="utf-8")

    loader = _Loader({
        "rewrite_rule": r"(?im)^[ \t]*RewriteRule[ \t]+\^/?([a-z0-9\-_/]+)\??\$?[ \t]+([^ \t]+)",
        "redirect": r"(?im)^[ \t]*Redirect(?:Permanent|[ \t]+3\d{2})?[ \t]+(/[^ \t]+)[ \t]+([^ \t]+)",
        "auto_stub_missing_routes": True,
        "fallback_target": "404.html",
    })
    stats = SimpleNamespace(
        htaccess_routes_initially_broken=0,
        htaccess_routes_autofixed=0,
        broken_htaccess_routes=0,
        warnings=0,
        errors=0,
    )

    result = collect_routes(tmp_path, loader, stats=stats)  # type: ignore[arg-type]

    assert result.routes["/broken"] == "missing.html"
    assert stats.htaccess_routes_initially_broken == 1
    assert stats.htaccess_routes_autofixed == 1
    assert stats.broken_htaccess_routes == 0


def test_collect_routes_handles_regex_with_extra_groups(tmp_path: Path) -> None:
    (tmp_path / ".htaccess").write_text(
        "RewriteRule ^broken$ missing.html\n",
        encoding="utf-8",
    )

    loader = _Loader({
        "rewrite_rule": (
            r"(?im)^[ \t]*RewriteRule[ \t]+\^/?(([a-z0-9\-_/]+))\??\$?[ \t]+([^ \t]+)"
        ),
        "redirect": r"(?im)^[ \t]*Redirect(?:Permanent|[ \t]+3\d{2})?[ \t]+(/[^ \t]+)[ \t]+([^ \t]+)",
        "remove_unresolved_routes": False,
    })
    result = collect_routes(tmp_path, loader)  # type: ignore[arg-type]

    assert result.routes["/broken"] == "missing.html"
    info = result.get_route_info("/broken")
    assert info is not None
    assert info.target == "missing.html"
