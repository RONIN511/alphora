"""
端口数据校验逻辑 —— 完整企业级实现
"""
import re
from typing import Any, List, Tuple, Dict, Type, Optional
import pandas as pd

from .schema import AgentInputPort, FieldSchema, DataType


# 自定义类型注册
_CUSTOM_TYPE_REGISTRY: Dict[str, Type] = {}


def register_custom_type(name: str, cls: Type) -> None:
    if not isinstance(cls, type):
        raise TypeError(f"'{cls}' is not a class")
    _CUSTOM_TYPE_REGISTRY[name] = cls


def get_custom_type(name: str) -> Optional[Type]:
    return _CUSTOM_TYPE_REGISTRY.get(name)


# 预编译正则缓存（提升性能）
_COMPILED_PATTERNS: Dict[str, re.Pattern] = {}


def _get_compiled_pattern(pattern: str) -> re.Pattern:
    if pattern not in _COMPILED_PATTERNS:
        _COMPILED_PATTERNS[pattern] = re.compile(pattern)
    return _COMPILED_PATTERNS[pattern]


def _validate_json(data: Any, fields: List[FieldSchema]) -> List[str]:
    if not isinstance(data, dict):
        return ["Expected a JSON object (dict), got: " + type(data).__name__]
    errors = []
    for f in fields:
        if f.required and f.name not in data:
            errors.append(f"Missing required field '{f.name}': {f.description or 'No description'}")
            continue
        if f.name in data:
            val = data[f.name]
            field_errors = _validate_field_value(val, f)
            for err in field_errors:
                errors.append(f"Field '{f.name}' ({f.description or 'no desc'}): {err}")
    return errors


def _validate_dataframe(data: Any, fields: List[FieldSchema]) -> List[str]:
    if not hasattr(data, 'columns') or not hasattr(data, 'shape'):
        return ["Expected a DataFrame-like object (must have 'columns' and 'shape')"]
    cols = set(data.columns)
    errors = []
    for f in fields:
        if f.required and f.name not in cols:
            errors.append(f"DataFrame missing required column: '{f.name}' ({f.description})")
    return errors


def _validate_field_value(value: Any, field: FieldSchema) -> List[str]:
    errors = []
    ft = field.type
    cons = field.constraints

    # === 类型检查（严格区分 bool 和 int/float）===
    if ft == "string":
        if not isinstance(value, str):
            errors.append(f"Expected string, got {type(value).__name__}")
    elif ft == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append("Expected integer (bool is not allowed)")
    elif ft == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append("Expected number (bool is not allowed)")
    elif ft == "boolean":
        if not isinstance(value, bool):
            errors.append("Expected boolean")
    elif ft == "array":
        if not isinstance(value, list):
            errors.append("Expected list")
    elif ft == "object":
        if not isinstance(value, dict):
            errors.append("Expected object (dict)")

    # === 约束检查 ===
    if isinstance(value, str):
        if cons:
            if cons.min_length is not None and len(value) < cons.min_length:
                errors.append(f"Length {len(value)} < minimum {cons.min_length}")
            if cons.max_length is not None and len(value) > cons.max_length:
                errors.append(f"Length {len(value)} > maximum {cons.max_length}")
            if cons.pattern is not None:
                pattern_re = _get_compiled_pattern(cons.pattern)
                if not pattern_re.fullmatch(value):
                    errors.append(f"Does not match pattern: {cons.pattern}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if cons:
            if cons.min_value is not None and value < cons.min_value:
                errors.append(f"Value {value} < minimum {cons.min_value}")
            if cons.max_value is not None and value > cons.max_value:
                errors.append(f"Value {value} > maximum {cons.max_value}")

    if cons and cons.enum is not None:
        if value not in cons.enum:
            errors.append(f"Value {repr(value)} not in allowed enum: {cons.enum}")

    return errors


def validate_port_data(port: AgentInputPort, data: Any) -> Tuple[bool, List[str]]:
    stype = port.schema_.data_type

    if stype in (DataType.JSON, DataType.DICT):
        errors = _validate_json(data, port.schema_.fields)
    elif stype == DataType.DATAFRAME:
        errors = _validate_dataframe(data, port.schema_.fields)
    elif stype == DataType.TEXT:
        errors = [] if isinstance(data, str) else [f"Expected str, got {type(data).__name__}"]
    elif stype == DataType.BYTES:
        errors = [] if isinstance(data, bytes) else [f"Expected bytes, got {type(data).__name__}"]
    elif stype == DataType.LIST:
        errors = [] if isinstance(data, list) else [f"Expected list, got {type(data).__name__}"]
    elif stype == DataType.CUSTOM:
        errors = []  # 由业务层处理
    else:
        # IMAGE, AUDIO 等二进制类型暂不校验内容
        errors = []

    return len(errors) == 0, errors