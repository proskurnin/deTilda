"""Small compatibility layer for Pydantic APIs used by Detilda.

If the real ``pydantic`` package is installed, this module re-exports its
classes. Otherwise it provides a minimal strict validator with a compatible
subset of APIs used in this repository.
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Union, get_args, get_origin, get_type_hints

if importlib.util.find_spec("pydantic") is not None:
    from pydantic import BaseModel, Field, ValidationError  # type: ignore
else:

    class ValidationError(ValueError):
        pass


    @dataclass(frozen=True)
    class _FieldInfo:
        default: Any = None
        default_factory: Any = None


    def Field(default: Any = None, *, default_factory: Any = None) -> _FieldInfo:
        return _FieldInfo(default=default, default_factory=default_factory)


    class BaseModel:
        def __init__(self, **kwargs: Any) -> None:
            hints = get_type_hints(self.__class__)
            for name, typ in hints.items():
                if name in kwargs:
                    value = kwargs[name]
                else:
                    default = getattr(self.__class__, name, None)
                    if isinstance(default, _FieldInfo):
                        if default.default_factory is not None:
                            value = default.default_factory()
                        else:
                            value = default.default
                    else:
                        value = default
                try:
                    coerced = self._coerce_type(value, typ, field_name=name)
                except ValidationError:
                    raise
                except Exception as exc:
                    raise ValidationError(str(exc)) from exc
                setattr(self, name, coerced)

        @classmethod
        def model_validate(cls, data: Mapping[str, Any]) -> "BaseModel":
            if not isinstance(data, Mapping):
                raise ValidationError(f"{cls.__name__}: expected mapping")
            return cls(**dict(data))

        @classmethod
        def parse_obj(cls, data: Mapping[str, Any]) -> "BaseModel":
            return cls.model_validate(data)

        def model_dump(self) -> Dict[str, Any]:
            out: Dict[str, Any] = {}
            hints = get_type_hints(self.__class__)
            for name in hints:
                value = getattr(self, name)
                out[name] = self._dump_value(value)
            return out

        def dict(self) -> Dict[str, Any]:
            return self.model_dump()

        @classmethod
        def _coerce_type(cls, value: Any, typ: Any, *, field_name: str) -> Any:
            origin = get_origin(typ)
            args = get_args(typ)

            if origin is Union:
                last_error: Exception | None = None
                for arg in args:
                    try:
                        return cls._coerce_type(value, arg, field_name=field_name)
                    except Exception as exc:
                        last_error = exc
                        continue
                raise ValidationError(f"{field_name}: invalid union value ({last_error})")

            if origin is list:
                if not isinstance(value, list):
                    raise ValidationError(f"{field_name}: expected list")
                item_type = args[0] if args else Any
                return [cls._coerce_type(item, item_type, field_name=field_name) for item in value]

            if origin is dict:
                if not isinstance(value, dict):
                    raise ValidationError(f"{field_name}: expected dict")
                key_type = args[0] if args else Any
                val_type = args[1] if len(args) > 1 else Any
                return {
                    cls._coerce_type(k, key_type, field_name=field_name): cls._coerce_type(v, val_type, field_name=field_name)
                    for k, v in value.items()
                }

            if typ is Any:
                return value
            if typ is str:
                if not isinstance(value, str):
                    raise ValidationError(f"{field_name}: expected str")
                return value
            if typ is bool:
                if not isinstance(value, bool):
                    raise ValidationError(f"{field_name}: expected bool")
                return value
            if typ is int:
                if not isinstance(value, int):
                    raise ValidationError(f"{field_name}: expected int")
                return value
            if typ is float:
                if not isinstance(value, (float, int)):
                    raise ValidationError(f"{field_name}: expected float")
                return float(value)
            if isinstance(typ, type) and issubclass(typ, BaseModel):
                if isinstance(value, typ):
                    return value
                if not isinstance(value, Mapping):
                    raise ValidationError(f"{field_name}: expected mapping for nested model")
                return typ.model_validate(value)
            return value

        @classmethod
        def _dump_value(cls, value: Any) -> Any:
            if isinstance(value, BaseModel):
                return value.model_dump()
            if isinstance(value, list):
                return [cls._dump_value(item) for item in value]
            if isinstance(value, dict):
                return {k: cls._dump_value(v) for k, v in value.items()}
            return value
