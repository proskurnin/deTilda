"""Tests for core.assets — main rename_and_cleanup_assets flow."""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "yaml" not in sys.modules:
    yaml_stub = types.ModuleType("yaml")
    yaml_stub.safe_load = lambda *_args, **_kwargs: {}
    sys.modules["yaml"] = yaml_stub

from core.assets import AssetResult, rename_and_cleanup_assets
from core.schemas import ImagesConfig, PatternsConfig, ServiceFilesConfig


class _FakeLoader:
    """Минимальный конфиг — без скачивания удалённых ассетов."""
    base_dir = ROOT

    def patterns(self) -> PatternsConfig:
        return PatternsConfig.model_validate({
            "assets": {"til_to_ai_filename": r"\btil"},
            "text_extensions": [".html"],
        })

    def images(self) -> ImagesConfig:
        return ImagesConfig.model_validate({
            "delete_physical_files": {
                "as_is": ["tildacopy.png", "logo404.png"],
            },
        })

    def service_files(self) -> ServiceFilesConfig:
        return ServiceFilesConfig.model_validate({
            "exclude_from_rename": {"files": ["robots.txt"]},
            "scripts_to_delete": {"files": []},
            "rename_map_output": {"filename": "{project}_rename_map.json", "location": "logs"},
        })


def test_renames_files_with_til_prefix(tmp_path: Path) -> None:
    """Файлы с til-префиксом переименовываются в ai-вариант."""
    (tmp_path / "tilda-block.css").write_text("body{}")
    (tmp_path / "normal.css").write_text("body{}")

    result = rename_and_cleanup_assets(tmp_path, loader=_FakeLoader())

    assert isinstance(result, AssetResult)
    assert (tmp_path / "aida-block.css").exists()
    assert not (tmp_path / "tilda-block.css").exists()
    assert (tmp_path / "normal.css").exists()  # не тронут
    assert result.stats.renamed >= 1


def test_deletes_as_is_files(tmp_path: Path) -> None:
    """Файлы из delete_physical_files.as_is удаляются."""
    (tmp_path / "tildacopy.png").write_bytes(b"fake")
    (tmp_path / "logo404.png").write_bytes(b"fake")
    (tmp_path / "keep.png").write_bytes(b"fake")

    result = rename_and_cleanup_assets(tmp_path, loader=_FakeLoader())

    assert not (tmp_path / "tildacopy.png").exists()
    assert not (tmp_path / "logo404.png").exists()
    assert (tmp_path / "keep.png").exists()
    assert result.stats.removed >= 2


class _PatternDeleteLoader(_FakeLoader):
    """Loader с regex-паттернами удаления — для UUID-имён вроде apple-touch-icon."""

    def images(self) -> ImagesConfig:
        return ImagesConfig.model_validate({
            "delete_physical_files": {
                "as_is": [],
                "patterns": [
                    r"apple-touch-icon-[0-9a-f]+\.png",
                    r"tilda-[a-z0-9]+-spec\.json",
                ],
            },
        })


def test_deletes_files_by_regex_pattern(tmp_path: Path) -> None:
    """Файлы, имя которых fullmatch'ит regex из patterns, удаляются до переименования."""
    (tmp_path / "apple-touch-icon-deadbeef.png").write_bytes(b"fake")
    (tmp_path / "Apple-Touch-Icon-CAFEBABE.png").write_bytes(b"fake")  # case-insensitive
    (tmp_path / "tilda-abc123-spec.json").write_bytes(b"{}")
    (tmp_path / "keep.png").write_bytes(b"fake")
    (tmp_path / "apple-touch-icon-precomposed.png").write_bytes(b"fake")  # не fullmatch

    result = rename_and_cleanup_assets(tmp_path, loader=_PatternDeleteLoader())

    assert not (tmp_path / "apple-touch-icon-deadbeef.png").exists()
    assert not (tmp_path / "Apple-Touch-Icon-CAFEBABE.png").exists()
    assert not (tmp_path / "tilda-abc123-spec.json").exists()
    assert (tmp_path / "keep.png").exists()
    # precomposed не удаляется — паттерн требует hex-suffix
    assert (tmp_path / "apple-touch-icon-precomposed.png").exists()
    assert result.stats.removed >= 3


def test_invalid_regex_pattern_logged_and_skipped(tmp_path: Path) -> None:
    """Битый regex не валит запуск — пишется warning, остальное работает."""

    class _BrokenPatternLoader(_FakeLoader):
        def images(self) -> ImagesConfig:
            return ImagesConfig.model_validate({
                "delete_physical_files": {
                    "as_is": ["logo404.png"],
                    "patterns": [r"[invalid(", r"valid-.*\.png"],
                },
            })

    (tmp_path / "logo404.png").write_bytes(b"fake")
    (tmp_path / "valid-x.png").write_bytes(b"fake")
    (tmp_path / "keep.png").write_bytes(b"fake")

    rename_and_cleanup_assets(tmp_path, loader=_BrokenPatternLoader())

    assert not (tmp_path / "logo404.png").exists()  # as_is работает
    assert not (tmp_path / "valid-x.png").exists()  # валидный паттерн работает
    assert (tmp_path / "keep.png").exists()


def test_excluded_files_not_renamed(tmp_path: Path) -> None:
    """Файлы из exclude_from_rename не переименовываются."""
    (tmp_path / "robots.txt").write_text("Disallow: /tilda")

    rename_and_cleanup_assets(tmp_path, loader=_FakeLoader())

    assert (tmp_path / "robots.txt").exists()


def test_creates_rename_map_json(tmp_path: Path) -> None:
    """rename_map.json сохраняется в logs/."""
    import core.logger as logger
    logger._project_name_var.set(tmp_path.name)
    logger._logs_dir_var.set(tmp_path / "logs")
    (tmp_path / "logs").mkdir()

    (tmp_path / "tilda-x.css").write_text("")

    rename_and_cleanup_assets(tmp_path, loader=_FakeLoader())

    map_files = list((tmp_path / "logs").glob("*_rename_map.json"))
    assert len(map_files) == 1


def test_creates_1px_placeholder(tmp_path: Path) -> None:
    """Создаётся images/1px.png — для замены логотипов Tilda в HTML."""
    rename_and_cleanup_assets(tmp_path, loader=_FakeLoader())

    placeholder = tmp_path / "images" / "1px.png"
    assert placeholder.exists()
    # Это валидный PNG (начинается с magic bytes)
    assert placeholder.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_raises_when_loader_missing(tmp_path: Path) -> None:
    """Без loader должен упасть с понятной ошибкой."""
    try:
        rename_and_cleanup_assets(tmp_path)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "ConfigLoader" in str(exc)


def test_returns_asset_result_with_stats(tmp_path: Path) -> None:
    """Возвращает AssetResult с rename_map и stats."""
    (tmp_path / "tilda-x.css").write_text("")

    result = rename_and_cleanup_assets(tmp_path, loader=_FakeLoader())

    assert isinstance(result.rename_map, dict)
    assert hasattr(result.stats, "renamed")
    assert hasattr(result.stats, "removed")
    assert hasattr(result.stats, "downloaded")


class _FaviconFallbackLoader(_FakeLoader):
    """Loader с правилами resource_copy для проверки if_missing."""

    def service_files(self) -> ServiceFilesConfig:
        return ServiceFilesConfig.model_validate({
            "exclude_from_rename": {"files": []},
            "scripts_to_delete": {"files": []},
            "rename_map_output": {"filename": "{project}_rename_map.json", "location": "logs"},
            "resource_copy": {
                "files": [
                    # Жёсткое копирование (без if_missing) — всегда перезаписывает
                    {"source": "favicon.ico", "destination": "images/favicon.ico"},
                    # Фолбэк в корень — копируется только если файла нет
                    {
                        "source": "favicon.ico",
                        "destination": "favicon.ico",
                        "if_missing": True,
                    },
                ],
            },
        })


def test_favicon_root_fallback_uses_resources_when_missing(tmp_path: Path) -> None:
    """if_missing=true — нет корневого favicon → копируем из resources/."""
    rename_and_cleanup_assets(tmp_path, loader=_FaviconFallbackLoader())

    target = tmp_path / "favicon.ico"
    assert target.exists()
    # Это файл из resources/, не пользовательский
    assert target.read_bytes() == (ROOT / "resources" / "favicon.ico").read_bytes()


def test_favicon_root_fallback_keeps_existing_user_file(tmp_path: Path) -> None:
    """if_missing=true — пользовательский favicon в корне не перезаписывается."""
    user_favicon = b"USER_FAVICON_BYTES"
    (tmp_path / "favicon.ico").write_bytes(user_favicon)

    rename_and_cleanup_assets(tmp_path, loader=_FaviconFallbackLoader())

    target = tmp_path / "favicon.ico"
    assert target.read_bytes() == user_favicon


def test_resource_copy_without_if_missing_overwrites(tmp_path: Path) -> None:
    """Без if_missing — старый файл перетирается (текущее поведение)."""
    target_dir = tmp_path / "images"
    target_dir.mkdir()
    (target_dir / "favicon.ico").write_bytes(b"OLD_BYTES")

    rename_and_cleanup_assets(tmp_path, loader=_FaviconFallbackLoader())

    # images/favicon.ico — без if_missing, должен быть перетёрт
    assert (target_dir / "favicon.ico").read_bytes() != b"OLD_BYTES"
