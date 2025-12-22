"""
数据契约模型 + 辅助工具方法

本模块定义了智能体（Agent）输入/输出端口的数据契约规范，
支持多模态数据类型（JSON、DataFrame、文本、图像等）和字段级约束，
可用于低代码平台、AI 编排系统或 FastAPI 接口自动生成。
"""

from __future__ import annotations

from typing import Any, List, Optional, Dict, Union, Type
from enum import Enum
from pydantic import BaseModel, Field, create_model, field_validator
import re


class AgentStatus(str, Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    FINISHED = 'finished'
    FAILED = 'failed'
    SUCCESS = 'success'


class DataType(str, Enum):
    """支持的数据类型枚举（语义化，非 Python 原生类型）"""
    JSON = "json"          # 结构化 JSON 对象（dict）
    DATAFRAME = "dataframe"  # 表格型数据（如 pandas.DataFrame）
    TEXT = "text"          # 纯文本字符串
    BYTES = "bytes"        # 二进制字节流
    IMAGE = "image"        # 图像数据（通常为 bytes 或 PIL.Image）
    AUDIO = "audio"        # 音频数据（通常为 bytes 或 numpy array）
    LIST = "list"          # 列表
    DICT = "dict"          # 字典（与 JSON 语义略有不同，常用于无 schema 场景）
    CUSTOM = "custom"      # 自定义对象（需配合 type_hint 使用）


class FieldConstraint(BaseModel):
    """字段的可选约束条件（用于校验和文档生成）"""

    min_value: Optional[Union[int, float]] = Field(
        default=None,
        description="数值型字段的最小允许值（包含）"
    )
    max_value: Optional[Union[int, float]] = Field(
        default=None,
        description="数值型字段的最大允许值（包含）"
    )
    min_length: Optional[int] = Field(
        default=None,
        description="字符串或列表的最小长度"
    )
    max_length: Optional[int] = Field(
        default=None,
        description="字符串或列表的最大长度"
    )
    pattern: Optional[str] = Field(
        default=None,
        description="字符串必须匹配的正则表达式（全匹配）"
    )
    enum: Optional[List[Any]] = Field(
        default=None,
        description="字段允许的取值列表"
    )

    @field_validator('pattern')
    @classmethod
    def _validate_regex(cls, v: str | None) -> str | None:
        """
        校验正则表达式是否合法。

        在模型实例化时自动调用，确保 pattern 字段是有效的正则。
        """
        if v is not None:
            try:
                re.compile(v)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern: {e}")
        return v


class FieldSchema(BaseModel):
    """描述结构化数据（如 JSON、DataFrame 列）中的一个字段"""

    name: str = Field(
        ...,
        description="字段名称，必须符合标识符规则（字母开头，可含数字和下划线）"
    )

    type: str = Field(
        ...,
        description="逻辑数据类型，支持：string | integer | number | boolean | object | array"
    )

    required: bool = Field(
        default=True,
        description="该字段是否为必需字段"
    )

    description: str = Field(
        default="",
        description="字段的语义描述，用于文档和错误提示"
    )

    example: Optional[Any] = Field(
        default=None,
        description="字段的示例值，用于文档生成和调试"
    )

    constraints: Optional[FieldConstraint] = Field(
        default=None,
        description="字段的附加约束条件"
    )


class PortSchema(BaseModel):
    """端口的数据契约定义（描述一个端口期望的数据格式）"""

    data_type: DataType = Field(
        ...,
        description="端口接收或输出的数据类型"
    )

    fields: List[FieldSchema] = Field(
        default_factory=list,
        description="当 data_type 为结构化类型（如 JSON）时，定义其内部字段"
    )

    type_hint: Optional[str] = Field(
        default=None,
        description="Python 类型提示字符串（如 'pandas.DataFrame'），用于 IDE 和文档"
    )


class AgentInputPort(BaseModel):
    """智能体的输入端口定义"""

    port: int = Field(default=8000, description='端口号')

    name: str = Field(
        ...,
        pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$",
        description="端口名称，必须是合法的 Python 标识符（字母开头）"
    )

    label: str = Field(
        default="",
        description="端口标签（如 'main_input'），用于 UI 分组或路由"
    )

    description: str = Field(
        default="",
        description="端口的详细说明"
    )

    required: bool = Field(
        default=True,
        description="该输入端口是否必须提供数据"
    )

    schema_: PortSchema = Field(
        ...,
        alias="schema",
        description="该端口的数据契约"
    )

    class Config:
        # 允许通过 schema_ 或 schema 访问字段（兼容别名）
        populate_by_name = True


class AgentOutputPort(BaseModel):
    """智能体的输出端口定义"""

    name: str = Field(
        ...,
        pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$",
        description="端口名称，必须是合法的 Python 标识符"
    )

    description: str = Field(
        default="",
        description="输出端口的说明"
    )

    schema_: PortSchema = Field(
        ...,
        alias="schema",
        description="该输出端口的数据契约"
    )

    class Config:
        populate_by_name = True


class AgentSpec(BaseModel):
    """智能体的完整规格定义（包含输入/输出端口契约）"""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$",
        description="智能体名称，必须是合法的 Python 标识符"
    )
    display_name: str = Field(
        default="",
        description="用于 UI 展示的友好名称"
    )
    description: str = Field(
        default="",
        description="智能体的功能描述"
    )
    version: str = Field(
        default="1.0.0",
        description="语义化版本号"
    )
    category: str = Field(
        default="",
        description="智能体分类（如 'nlp', 'vision', 'data_processing'）"
    )
    input_ports: List[AgentInputPort] = Field(
        default_factory=list,
        description="该智能体支持的所有输入端口"
    )
    output_ports: List[AgentOutputPort] = Field(
        default_factory=list,
        description="该智能体产生的所有输出端口"
    )

    def get_input_port(self, name: str) -> Optional[AgentInputPort]:
        """
        根据端口名称查找输入端口。

        Args:
            name: 输入端口名称

        Returns:
            InputPort 实例，若未找到则返回 None
        """
        for port in self.input_ports:
            if port.name == name:
                return port
        return None

    def validate_input(self, port_name: str, data: Any) -> tuple[bool, list[str]]:
        """
        校验输入数据是否符合指定端口的契约。

        注意：实际校验逻辑在 validation.py 中实现（此处为委托调用）。

        Args:
            port_name: 要校验的输入端口名称
            data: 待校验的数据

        Returns:
            (是否通过校验, 错误信息列表)
        """
        from .validation import validate_port_data
        port = self.get_input_port(port_name)
        if not port:
            return False, [f"Input port '{port_name}' not found"]
        return validate_port_data(port, data)

    def to_pydantic_model(self, port_name: str) -> Optional[type[BaseModel]]:
        """
        为 JSON/DICT 类型的输入端口动态生成 Pydantic 模型。

        适用于 FastAPI 自动请求体解析和文档生成。

        Args:
            port_name: 输入端口名称

        Returns:
            动态生成的 Pydantic 模型类，若端口不支持则返回 None
        """
        port = self.get_input_port(port_name)
        if not port or port.schema_.data_type not in (DataType.JSON, DataType.DICT):
            return None

        field_defs = {}
        for f in port.schema_.fields:
            # 将逻辑类型映射为 Python 类型
            py_type_map = {
                "string": str,
                "integer": int,
                "number": float,
                "boolean": bool,
                "array": list,
                "object": dict,
            }
            base_type = py_type_map.get(f.type, Any)

            # 构建 Field 信息
            field_info_kwargs = {"description": f.description}
            if f.example is not None:
                field_info_kwargs["examples"] = [f.example]

            if f.required:
                field_defs[f.name] = (base_type, Field(default=..., **field_info_kwargs))
            else:
                field_defs[f.name] = (Optional[base_type], Field(default=None, **field_info_kwargs))

        model_name = f"{self.name}_{port_name.title()}Input"
        return create_model(model_name, **field_defs)

    def to_openapi_components(self) -> Dict[str, Any]:
        """
        生成 OpenAPI 3.0 的 components.schemas 片段。

        仅处理 JSON/DICT 类型的输入端口，用于 Swagger UI 文档。

        Returns:
            符合 OpenAPI 规范的 schemas 字典
        """
        schemas = {}
        for port in self.input_ports:
            if port.schema_.data_type in (DataType.JSON, DataType.DICT):
                props = {}
                required = []
                for f in port.schema_.fields:
                    # 构建 OpenAPI 属性定义
                    prop = {
                        "type": f.type,
                        "description": f.description,
                    }
                    if f.example is not None:
                        prop["example"] = f.example
                    if f.constraints:
                        cons = f.constraints
                        if cons.min_value is not None:
                            prop["minimum"] = cons.min_value
                        if cons.max_value is not None:
                            prop["maximum"] = cons.max_value
                        if cons.min_length is not None:
                            prop["minLength"] = cons.min_length
                        if cons.max_length is not None:
                            prop["maxLength"] = cons.max_length
                        if cons.pattern is not None:
                            prop["pattern"] = cons.pattern
                        if cons.enum is not None:
                            prop["enum"] = cons.enum
                    props[f.name] = prop
                    if f.required:
                        required.append(f.name)

                schemas[f"{self.name}_{port.name}_input"] = {
                    "type": "object",
                    "properties": props,
                    "required": required,
                }
        return schemas

    def describe(self) -> Dict[str, Any]:
        """
        返回智能体的完整可读性描述。

        适用于 UI 展示、日志记录或调试信息。

        Returns:
            包含所有元信息和端口详情的字典
        """
        return {
            "name": self.name,
            "display_name": self.display_name or self.name,
            "description": self.description,
            "version": self.version,
            "category": self.category,
            "inputs": [
                {
                    "name": p.name,
                    "description": p.description,
                    "type": p.schema_.data_type,
                    "fields": [f.model_dump(exclude_defaults=True) for f in p.schema_.fields]
                }
                for p in self.input_ports
            ],
            "outputs": [
                {
                    "name": p.name,
                    "description": p.description,
                    "type": p.schema_.data_type,
                    "fields": [f.model_dump(exclude_defaults=True) for f in p.schema_.fields]
                }
                for p in self.output_ports
            ]
        }