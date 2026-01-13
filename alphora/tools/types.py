"""
alphora.tools.types - 核心类型定义

设计原则：
1. 简单清晰的数据结构
2. 完整的类型注解
3. 支持序列化和LLM交互
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Dict, List, Optional, Union, TypeVar, Generic
from dataclasses import dataclass, field
from datetime import datetime


# ==================== 工具执行状态 ====================

class ToolStatus(str, Enum):
    """工具执行状态"""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    PENDING = "pending"
    RUNNING = "running"


# ==================== 工具执行结果 ====================

T = TypeVar('T')

@dataclass
class ToolResult(Generic[T]):
    """
    工具执行结果

    设计目标：
    - 统一的结果格式
    - 支持泛型数据类型
    - 便捷的链式操作
    - 丰富的元数据

    Examples:
        >>> result = ToolResult.ok({"sql": "SELECT...", "data": [...]})
        >>> if result.success:
        ...     print(result.data)

        >>> result = ToolResult.fail("数据源连接失败")
        >>> print(result.error)
    """
    status: ToolStatus
    data: Optional[T] = None
    error: Optional[str] = None

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 执行追踪
    tool_name: Optional[str] = None
    call_id: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: Optional[float] = None

    # 用于流式输出的中间结果
    intermediate_results: List[Any] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """是否执行成功"""
        return self.status == ToolStatus.SUCCESS

    @property
    def failed(self) -> bool:
        """是否执行失败"""
        return self.status in (ToolStatus.ERROR, ToolStatus.TIMEOUT, ToolStatus.CANCELLED)

    # ==================== 工厂方法 ====================

    @classmethod
    def ok(cls, data: T = None, **metadata) -> ToolResult[T]:
        """创建成功结果"""
        return cls(status=ToolStatus.SUCCESS, data=data, metadata=metadata)

    @classmethod
    def fail(cls, error: str, **metadata) -> ToolResult[T]:
        """创建失败结果"""
        return cls(status=ToolStatus.ERROR, error=error, metadata=metadata)

    @classmethod
    def timeout(cls, error: str = "执行超时", **metadata) -> ToolResult[T]:
        """创建超时结果"""
        return cls(status=ToolStatus.TIMEOUT, error=error, metadata=metadata)

    # ==================== 链式操作 ====================

    def map(self, func) -> ToolResult:
        """对成功结果应用函数"""
        if self.success:
            try:
                return ToolResult.ok(func(self.data), **self.metadata)
            except Exception as e:
                return ToolResult.fail(str(e))
        return self

    def flat_map(self, func) -> ToolResult:
        """对成功结果应用返回 ToolResult 的函数"""
        if self.success:
            try:
                return func(self.data)
            except Exception as e:
                return ToolResult.fail(str(e))
        return self

    def or_else(self, default: T) -> T:
        """获取数据或默认值"""
        return self.data if self.success else default

    def unwrap(self) -> T:
        """获取数据，失败时抛出异常"""
        if self.success:
            return self.data
        raise ValueError(self.error or "Unknown error")

    # ==================== 序列化 ====================

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "status": self.status.value,
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata,
            "tool_name": self.tool_name,
            "call_id": self.call_id,
            "duration_ms": self.duration_ms,
        }

    def to_json(self) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    def to_llm_content(self) -> str:
        """转换为 LLM 可理解的内容格式"""
        if self.success:
            if isinstance(self.data, (dict, list)):
                return json.dumps(self.data, ensure_ascii=False, indent=2)
            return str(self.data) if self.data is not None else "执行成功"
        return f"执行失败: {self.error}"

    def __str__(self) -> str:
        return self.to_llm_content()


# ==================== 工具调用 ====================

@dataclass
class ToolCall:
    """
    工具调用请求

    表示一次工具调用的完整信息
    支持从不同 LLM 格式解析
    """
    id: str
    name: str
    arguments: Dict[str, Any]

    # 上下文信息
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ToolCall:
        return cls(
            id=data.get("id", ""),
            name=data["name"],
            arguments=data.get("arguments", {}),
            context=data.get("context", {}),
        )

    @classmethod
    def from_openai(cls, tool_call) -> ToolCall:
        """从 OpenAI 格式解析"""
        if hasattr(tool_call, 'function'):
            return cls(
                id=tool_call.id,
                name=tool_call.function.name,
                arguments=json.loads(tool_call.function.arguments),
            )
        elif isinstance(tool_call, dict):
            func = tool_call.get('function', tool_call)
            args = func.get('arguments', {})
            if isinstance(args, str):
                args = json.loads(args)
            return cls(
                id=tool_call.get('id', ''),
                name=func['name'],
                arguments=args,
            )
        raise ValueError(f"Unsupported tool call format: {type(tool_call)}")

    @classmethod
    def from_anthropic(cls, tool_use_block) -> ToolCall:
        """从 Anthropic 格式解析"""
        if hasattr(tool_use_block, 'name'):
            return cls(
                id=getattr(tool_use_block, 'id', ''),
                name=tool_use_block.name,
                arguments=tool_use_block.input if hasattr(tool_use_block, 'input') else {},
            )
        elif isinstance(tool_use_block, dict):
            return cls(
                id=tool_use_block.get('id', ''),
                name=tool_use_block['name'],
                arguments=tool_use_block.get('input', {}),
            )
        raise ValueError(f"Unsupported Anthropic tool call format: {type(tool_use_block)}")


# ==================== 工具 Schema ====================

@dataclass
class ToolParameter:
    """工具参数定义"""
    name: str
    type: str  # JSON Schema 类型
    description: str = ""
    required: bool = True
    default: Any = None
    enum: Optional[List[Any]] = None

    def to_json_schema(self) -> Dict[str, Any]:
        schema = {
            "type": self.type,
            "description": self.description,
        }
        if self.enum:
            schema["enum"] = self.enum
        return schema


@dataclass
class ToolSchema:
    """
    工具的完整 Schema 定义

    用于生成 LLM 可用的工具定义
    """
    name: str
    description: str
    parameters: List[ToolParameter] = field(default_factory=list)

    # 元数据
    tags: List[str] = field(default_factory=list)
    examples: List[Dict[str, Any]] = field(default_factory=list)

    def to_json_schema(self) -> Dict[str, Any]:
        """生成 JSON Schema"""
        properties = {}
        required = []

        for param in self.parameters:
            properties[param.name] = param.to_json_schema()
            if param.required:
                required.append(param.name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def to_openai_function(self) -> Dict[str, Any]:
        """转换为 OpenAI Function Calling 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.to_json_schema(),
            }
        }

    def to_anthropic_tool(self) -> Dict[str, Any]:
        """转换为 Anthropic Tool Use 格式"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.to_json_schema(),
        }


# ==================== 配置和依赖 ====================

@dataclass
class ToolConfig:
    """工具配置"""
    timeout: float = 60.0
    max_retries: int = 3
    cache_enabled: bool = False
    cache_ttl: float = 300.0

    # 运行时依赖
    dependencies: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.dependencies.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.dependencies[key] = value


# ==================== 类型别名 ====================

ToolInput = Dict[str, Any]
ToolOutput = Union[ToolResult, Any]
ToolHandler = Any  # Callable[[ToolInput], Awaitable[ToolOutput]]
