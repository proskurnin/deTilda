from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

yaml_stub = sys.modules.get("yaml")
if yaml_stub is None:
    yaml_stub = types.ModuleType("yaml")
    yaml_stub.safe_load = lambda *_args, **_kwargs: {}
    sys.modules["yaml"] = yaml_stub

from core.htaccess import collect_routes, get_route_info


class _Loader:
    def __init__(self, htaccess_patterns: dict[str, object]) -> None:
        self._htaccess_patterns = htaccess_patterns

    def patterns(self) -> dict[str, object]:
        return {"htaccess_patterns": self._htaccess_patterns}


def test_collect_routes_soft_fallback_to_404(tmp_path: Path) -> None:
    (tmp_path / ".htaccess").write_text(
        "RewriteRule ^broken$ missing.html\n",
        encoding="utf-8",
    )
    (tmp_path / "404.html").write_text("<h1>404</h1>", encoding="utf-8")

    loader = _Loader(
        {
                "rewrite_rule": r"(?im)^[ \t]*RewriteRule[ \t]+\^/?([a-z0-9\-_/]+)\??\$?[ \t]+([^ \t]+)",
                "redirect": r"(?im)^[ \t]*Redirect(?:Permanent|[ \t]+3\d{2})?[ \t]+(/[^ \t]+)[ \t]+([^ \t]+)",
            "soft_fallback_to_404": True,
            "fallback_target": "404.html",
        }
    )
    routes = collect_routes(tmp_path, loader)  # type: ignore[arg-type]

    assert routes["/broken"] == "404.html"
    info = get_route_info("/broken")
    assert info is not None
    assert info.exists
    assert info.target == "404.html"


def test_collect_routes_without_soft_fallback_keeps_broken_target(tmp_path: Path) -> None:
    (tmp_path / ".htaccess").write_text(
        "RewriteRule ^broken$ missing.html\n",
        encoding="utf-8",
    )

    loader = _Loader(
        {
                "rewrite_rule": r"(?im)^[ \t]*RewriteRule[ \t]+\^/?([a-z0-9\-_/]+)\??\$?[ \t]+([^ \t]+)",
                "redirect": r"(?im)^[ \t]*Redirect(?:Permanent|[ \t]+3\d{2})?[ \t]+(/[^ \t]+)[ \t]+([^ \t]+)",
            "soft_fallback_to_404": False,
        }
    )
    routes = collect_routes(tmp_path, loader)  # type: ignore[arg-type]

    assert routes["/broken"] == "missing.html"
    info = get_route_info("/broken")
    assert info is not None
    assert not info.exists
    assert info.target == "missing.html"
