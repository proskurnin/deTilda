"""Tests for core.pydantic_compat — our minimal pydantic replacement.

Покрывает обе ветки:
  - если pydantic установлен — тестируем реальный API (должен быть совместим)
  - если pydantic нет — тестируем нашу реализацию

Тесты должны проходить в обоих случаях.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from core.pydantic_compat import BaseModel, ConfigDict, Field, ValidationError


# ---------- Базовые модели ----------

class _Simple(BaseModel):
    name: str
    age: int


class _WithDefaults(BaseModel):
    name: str = "default_name"
    count: int = 0


class _WithFactory(BaseModel):
    items: List[str] = Field(default_factory=list)
    mapping: Dict[str, int] = Field(default_factory=dict)


class _Nested(BaseModel):
    inner: _Simple
    label: str = ""


class _WithOptional(BaseModel):
    value: Optional[str] = None


# ---------- Создание модели ----------

def test_basic_creation_with_kwargs() -> None:
    m = _Simple(name="alice", age=30)
    assert m.name == "alice"
    assert m.age == 30


def test_defaults_applied_when_field_missing() -> None:
    m = _WithDefaults()
    assert m.name == "default_name"
    assert m.count == 0


def test_defaults_overridden_by_kwargs() -> None:
    m = _WithDefaults(name="custom", count=42)
    assert m.name == "custom"
    assert m.count == 42


def test_default_factory_creates_fresh_instance() -> None:
    """default_factory должен вызываться для каждой модели — не shared mutable."""
    m1 = _WithFactory()
    m2 = _WithFactory()
    m1.items.append("x")
    # Если factory не работает корректно — m2.items тоже будет содержать "x"
    assert m2.items == [] or m2.items != m1.items


# ---------- model_validate ----------

def test_model_validate_from_dict() -> None:
    m = _Simple.model_validate({"name": "bob", "age": 25})
    assert m.name == "bob"
    assert m.age == 25


def test_parse_obj_is_alias_for_model_validate() -> None:
    """parse_obj — legacy API pydantic v1, должен работать."""
    m = _Simple.parse_obj({"name": "bob", "age": 25})
    assert m.name == "bob"


def test_model_validate_rejects_non_mapping() -> None:
    with pytest.raises((ValidationError, ValueError, TypeError)):
        _Simple.model_validate("not a dict")  # type: ignore[arg-type]


def test_validation_error_on_type_mismatch() -> None:
    """Несоответствие типов выбрасывает ValidationError."""
    with pytest.raises((ValidationError, ValueError, TypeError)):
        _Simple.model_validate({"name": "x", "age": "not-a-number"})


# ---------- model_dump ----------

def test_model_dump_returns_dict() -> None:
    m = _Simple(name="x", age=1)
    data = m.model_dump()
    assert data == {"name": "x", "age": 1}


def test_dict_method_is_alias_for_model_dump() -> None:
    """.dict() — legacy API, должен работать."""
    m = _Simple(name="x", age=1)
    assert m.dict() == m.model_dump()


def test_model_dump_recursive_for_nested() -> None:
    """Вложенные BaseModel должны сериализоваться рекурсивно."""
    m = _Nested(inner=_Simple(name="a", age=1), label="L")
    data = m.model_dump()
    assert data == {"inner": {"name": "a", "age": 1}, "label": "L"}


# ---------- Вложенные модели ----------

def test_nested_model_validation_from_dict() -> None:
    """Вложенный BaseModel автоматически создаётся из словаря."""
    m = _Nested.model_validate({"inner": {"name": "a", "age": 1}, "label": "L"})
    assert isinstance(m.inner, _Simple)
    assert m.inner.name == "a"
    assert m.label == "L"


# ---------- Контейнеры ----------

def test_list_of_strings_validated() -> None:
    m = _WithFactory.model_validate({"items": ["a", "b"], "mapping": {}})
    assert m.items == ["a", "b"]


def test_dict_of_strings_to_ints_validated() -> None:
    m = _WithFactory.model_validate({"items": [], "mapping": {"x": 1}})
    assert m.mapping == {"x": 1}


# ---------- Optional/Union ----------

def test_optional_accepts_none() -> None:
    m = _WithOptional(value=None)
    assert m.value is None


def test_optional_accepts_string() -> None:
    m = _WithOptional(value="hello")
    assert m.value == "hello"


# ---------- ConfigDict ----------

def test_config_dict_is_callable() -> None:
    """ConfigDict — заглушка/no-op, но должна вызываться без ошибок."""
    cfg = ConfigDict(frozen=True, extra="allow")
    assert cfg is not None


# ---------- Интеграция со схемами проекта ----------

def test_real_schema_loads_and_dumps() -> None:
    """Smoke-test: реальная схема проекта работает через наш compat-слой."""
    from core.schemas import PatternsConfig

    cfg = PatternsConfig.model_validate({
        "links": ["pattern1"],
        "text_extensions": [".html"],
        "ignore_prefixes": ["http://"],
    })
    assert cfg.links == ["pattern1"]
    assert cfg.text_extensions == [".html"]
    assert cfg.ignore_prefixes == ["http://"]

    # Дефолты для незаданных полей
    assert cfg.replace_rules == []
    assert cfg.tilda_remnants_patterns == []
