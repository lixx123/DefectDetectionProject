"""UTF-8 JSON codec. Unknown additive fields are preserved at their original level."""
from dataclasses import fields, is_dataclass
from enum import Enum
from functools import lru_cache
import json
import math
from pathlib import Path
from types import UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints


@lru_cache(maxsize=None)
def _hints(cls):
    return get_type_hints(cls)


def _encode(value):
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        result = dict(getattr(value, "_unknown_fields", {}))
        for f in fields(value):
            if not f.name.startswith("_"):
                result[f.name] = _encode(getattr(value, f.name))
        return result
    if isinstance(value, dict):
        if any(not isinstance(k, str) for k in value):
            raise TypeError("JSON object keys must be strings")
        return {k: _encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(v) for v in value]
    if value is None or type(value) in (str, bool, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise TypeError(f"unsupported JSON value {type(value).__name__}; use ArtifactReference for paths/images")


def _decode(annotation, value, location):
    if annotation is Any:
        return _encode(value)
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, UnionType):
        if value is None and type(None) in args:
            return None
        errors = []
        for arg in args:
            if arg is type(None):
                continue
            try:
                return _decode(arg, value, location)
            except (TypeError, ValueError) as exc:
                errors.append(str(exc))
        raise ValueError(f"{location}: no valid union type ({'; '.join(errors)})")
    if annotation is type(None):
        if value is not None:
            raise TypeError(f"{location}: expected null")
        return None
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        try:
            return annotation(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{location}: unknown {annotation.__name__} value {value!r}") from exc
    if is_dataclass(annotation):
        if not isinstance(value, dict):
            raise TypeError(f"{location}: expected object")
        retired = set(value) & getattr(annotation, "_retired_wire_fields", frozenset())
        if retired:
            raise ValueError(f"{location}: removed pre-freeze plan fields {sorted(retired)}; use attempts[].plan")
        hints = _hints(annotation)
        accepted = {f.name for f in fields(annotation) if f.init and not f.name.startswith('_')}
        kwargs = {k: _decode(hints[k], v, f"{location}.{k}") for k, v in value.items() if k in accepted}
        try:
            obj = annotation(**kwargs)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{location}: {exc}") from exc
        unknown = {k: _encode(v) for k, v in value.items() if k not in accepted}
        if unknown:
            object.__setattr__(obj, "_unknown_fields", unknown)
        return obj
    if origin in (list, tuple) or annotation in (list, tuple):
        if not isinstance(value, list):
            raise TypeError(f"{location}: expected array")
        subtype = args[0] if args else Any
        result = [_decode(subtype, v, f"{location}[{i}]") for i, v in enumerate(value)]
        return tuple(result) if origin is tuple or annotation is tuple else result
    if origin is dict or annotation is dict:
        if not isinstance(value, dict):
            raise TypeError(f"{location}: expected object")
        keytype, subtype = args if args else (str, Any)
        return {_decode(keytype, k, location): _decode(subtype, v, f"{location}.{k}") for k, v in value.items()}
    if annotation is float and type(value) in (float, int) and math.isfinite(value):
        return float(value)
    if annotation in (str, bool, int) and type(value) is annotation:
        return value
    raise TypeError(f"{location}: expected {annotation}, got {type(value).__name__}")


def to_dict(model) -> dict:
    payload = _encode(model)
    # Enforce type hints and validators again, also after mutable fields change.
    _decode(type(model), payload, type(model).__name__)
    return payload


def from_dict(cls, payload: dict):
    return _decode(cls, payload, cls.__name__)


def dumps(model) -> str:
    return json.dumps(to_dict(model), ensure_ascii=False, indent=2, allow_nan=False)


def _reject_constant(value):
    raise ValueError(f"non-finite JSON number: {value}")


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate JSON key: {key}")
        obj[key] = value
    return obj


def parse_json(text: str) -> dict:
    result = json.loads(text, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    if not isinstance(result, dict):
        raise ValueError("result JSON must be an object")
    return result
