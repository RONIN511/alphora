"""
alphora.tools.tool - 工具定义核心模块

设计目标：
1. 极简的工具定义方式 - @tool 装饰器
2. 支持子Agent作为工具 - @agent_tool
3. 自动类型推断和文档生成
4. 依赖注入支持

解决的痛点：
- 之前：手动写prompt模拟工具路由，用if/else分发
- 现在：声明式定义工具，框架自动处理路由和执行
"""

from __future__ import annotations

import re
import json
import inspect
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import (
    Any, Callable, Dict, List, Optional, Type, TypeVar, Union,
    get_type_hints, Awaitable, Generic, Protocol, runtime_checkable
)
from functools import wraps
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, create_model

from .types import ToolResult, ToolSchema, ToolParameter, ToolConfig, ToolCall

logger = logging.getLogger(__name__)

T = TypeVar('T')
F = TypeVar('F', bound=Callable[..., Any])


# ==================== Python 类型到 JSON Schema ====================

def python_type_to_json_schema(py_type: Type) -> Dict[str, Any]:
    """将 Python 类型转换为 JSON Schema 类型"""

    type_mapping = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        bytes: {"type": "string", "format": "byte"},
        type(None): {"type": "null"},
        list: {"type": "array"},
        dict: {"type": "object"},
    }

    if py_type in type_mapping:
        return type_mapping[py_type]

    # 处理泛型
    origin = getattr(py_type, '__origin__', None)
    args = getattr(py_type, '__args__', ())

    if origin is list or (hasattr(py_type, '__name__') and py_type.__name__ == 'List'):
        item_schema = python_type_to_json_schema(args[0]) if args else {}
        return {"type": "array", "items": item_schema}

    if origin is dict:
        return {"type": "object"}

    if origin is Union:
        non_none_types = [t for t in args if t is not type(None)]
        if len(non_none_types) == 1:
            return python_type_to_json_schema(non_none_types[0])
        return {"anyOf": [python_type_to_json_schema(t) for t in non_none_types]}

    # Pydantic 模型
    if isinstance(py_type, type) and issubclass(py_type, BaseModel):
        return py_type.model_json_schema()

    # Enum
    from enum import Enum
    if isinstance(py_type, type) and issubclass(py_type, Enum):
        return {"type": "string", "enum": [e.value for e in py_type]}

    return {"type": "string"}


def get_json_type(py_type: Type) -> str:
    """获取 JSON Schema 类型字符串"""
    schema = python_type_to_json_schema(py_type)
    return schema.get("type", "string")


# ==================== Docstring 解析 ====================

def parse_docstring(docstring: Optional[str]) -> tuple[str, Dict[str, str]]:
    """
    解析 docstring，提取描述和参数说明
    支持 Google 风格和 Sphinx 风格
    """
    if not docstring:
        return "", {}

    lines = docstring.strip().split('\n')

    # 提取描述
    description_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.lower().startswith(('args:', 'arguments:', 'parameters:', ':param')):
            break
        description_lines.append(stripped)
    description = ' '.join(description_lines)

    # 解析参数
    params = {}

    # Google 风格
    args_match = re.search(
        r'(?:Args?|Arguments?|Parameters?):\s*\n((?:[ \t]+\w+.*\n?)+)',
        docstring, re.IGNORECASE
    )
    if args_match:
        args_section = args_match.group(1)
        for match in re.finditer(
                r'^[ \t]+(\w+)(?:\s*\([^)]*\))?:\s*(.+?)(?=\n[ \t]+\w+|\n\n|\n[ \t]*$|\Z)',
                args_section, re.MULTILINE | re.DOTALL
        ):
            params[match.group(1)] = ' '.join(match.group(2).strip().split())
        return description, params

    # Sphinx 风格
    for match in re.finditer(r':param\s+(\w+):\s*(.+?)(?=:|$)', docstring, re.MULTILINE):
        params[match.group(1)] = match.group(2).strip()

    return description, params


# ==================== 工具基类 ====================

class Tool(ABC):
    """
    工具基类

    工具是可被 LLM 调用的原子操作单元。

    特点：
    - 有明确的输入输出定义
    - 可以被 LLM 通过 Function Calling 调用
    - 支持依赖注入

    使用方式：
    1. 继承 Tool 类
    2. 使用 @tool 装饰器（推荐）
    """

    # 子类可覆盖
    name: str = ""
    description: str = ""
    tags: List[str] = []

    # 运行时配置
    _config: Optional[ToolConfig] = None

    def __init__(self):
        if not self.name:
            self.name = self._infer_name()
        self._schema: Optional[ToolSchema] = None

    def _infer_name(self) -> str:
        """从类名推断工具名称"""
        name = self.__class__.__name__
        if name.endswith('Tool'):
            name = name[:-4]
        # 驼峰转下划线
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    @abstractmethod
    async def run(self, **kwargs) -> ToolResult:
        """执行工具，子类必须实现"""
        pass

    def run_sync(self, **kwargs) -> ToolResult:
        """同步执行"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.run(**kwargs))

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, self.run(**kwargs))
            return future.result()

    async def __call__(self, **kwargs) -> ToolResult:
        """使工具可调用"""
        return await self.run(**kwargs)

    # ==================== Schema 生成 ====================

    def get_schema(self) -> ToolSchema:
        """获取工具 Schema"""
        if self._schema is None:
            self._schema = self._build_schema()
        return self._schema

    def _build_schema(self) -> ToolSchema:
        """从 run 方法构建 Schema"""
        sig = inspect.signature(self.run)
        hints = get_type_hints(self.run) if hasattr(self.run, '__annotations__') else {}
        _, param_descriptions = parse_docstring(self.run.__doc__)

        parameters = []
        for param_name, param in sig.parameters.items():
            if param_name in ('self', 'cls', 'kwargs'):
                continue

            param_type = hints.get(param_name, str)
            has_default = param.default is not inspect.Parameter.empty

            parameters.append(ToolParameter(
                name=param_name,
                type=get_json_type(param_type),
                description=param_descriptions.get(param_name, ""),
                required=not has_default,
                default=param.default if has_default else None,
            ))

        return ToolSchema(
            name=self.name,
            description=self.description or parse_docstring(self.__doc__)[0],
            parameters=parameters,
            tags=self.tags,
        )

    def to_openai(self) -> Dict[str, Any]:
        """转换为 OpenAI 格式"""
        return self.get_schema().to_openai_function()

    def to_anthropic(self) -> Dict[str, Any]:
        """转换为 Anthropic 格式"""
        return self.get_schema().to_anthropic_tool()

    # ==================== 依赖注入 ====================

    def configure(self, config: ToolConfig) -> Tool:
        """配置工具"""
        self._config = config
        return self

    def get_dependency(self, key: str, default: Any = None) -> Any:
        """获取依赖"""
        if self._config:
            return self._config.get(key, default)
        return default

    def __repr__(self) -> str:
        return f"<Tool: {self.name}>"


# ==================== 函数工具 ====================

class FunctionTool(Tool):
    """
    从函数创建的工具

    支持同步和异步函数
    """

    def __init__(
            self,
            func: Callable,
            name: Optional[str] = None,
            description: Optional[str] = None,
            tags: Optional[List[str]] = None,
    ):
        self._func = func
        self._is_async = inspect.iscoroutinefunction(func)

        # 解析 docstring
        doc_description, self._param_descriptions = parse_docstring(func.__doc__)

        # 设置属性
        self.name = name or func.__name__
        self.description = description or doc_description or ""
        self.tags = tags or []

        super().__init__()

        # 保留原函数属性
        self.__doc__ = func.__doc__
        self.__name__ = func.__name__

    def _build_schema(self) -> ToolSchema:
        """从函数签名构建 Schema"""
        sig = inspect.signature(self._func)
        hints = get_type_hints(self._func) if hasattr(self._func, '__annotations__') else {}

        parameters = []
        for param_name, param in sig.parameters.items():
            if param_name in ('self', 'cls'):
                continue

            param_type = hints.get(param_name, str)
            has_default = param.default is not inspect.Parameter.empty

            parameters.append(ToolParameter(
                name=param_name,
                type=get_json_type(param_type),
                description=self._param_descriptions.get(param_name, ""),
                required=not has_default,
                default=param.default if has_default else None,
            ))

        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=parameters,
            tags=self.tags,
        )

    async def run(self, **kwargs) -> ToolResult:
        """执行函数"""
        try:
            if self._is_async:
                result = await self._func(**kwargs)
            else:
                result = self._func(**kwargs)

            if isinstance(result, ToolResult):
                return result
            return ToolResult.ok(result)

        except Exception as e:
            logger.exception(f"Tool {self.name} execution failed")
            return ToolResult.fail(str(e))


# ==================== @tool 装饰器 ====================

def tool(
        func: Optional[F] = None,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
) -> Union[FunctionTool, Callable[[F], FunctionTool]]:
    """
    工具装饰器

    将函数转换为 Tool，自动从函数签名和 docstring 提取信息

    Examples:
        简单用法：
        >>> @tool
        ... def greet(name: str) -> str:
        ...     '''向用户打招呼'''
        ...     return f"Hello, {name}!"

        完整参数：
        >>> @tool(name="data_query", description="查询数据", tags=["data"])
        ... async def query(sql: str, source_id: str) -> dict:
        ...     '''执行数据查询
        ...
        ...     Args:
        ...         sql: SQL 语句
        ...         source_id: 数据源 ID
        ...     '''
        ...     return await execute_sql(sql, source_id)
    """
    def decorator(fn: F) -> FunctionTool:
        return FunctionTool(
            func=fn,
            name=name,
            description=description,
            tags=tags,
        )

    if func is not None:
        return decorator(func)
    return decorator


# ==================== Agent 工具协议 ====================

@runtime_checkable
class AgentProtocol(Protocol):
    """Agent 协议，定义可作为工具的 Agent 接口"""

    async def run(self, **kwargs) -> Any:
        """执行 Agent"""
        ...


# ==================== Agent 作为工具 ====================

class AgentTool(Tool):
    """
    将 Agent 包装为工具

    解决痛点：
    - 之前：手动 derive() 创建子Agent，手动传递配置
    - 现在：声明式定义Agent工具，框架自动处理配置传递

    Examples:
        >>> @agent_tool(
        ...     name="data_query",
        ...     description="执行数据查询",
        ...     requires=['dacos_client', 'source_id']  # 声明依赖
        ... )
        ... class DataQueryAgent(BaseAgent):
        ...     async def run(self, query: str) -> ToolResult:
        ...         client = self.get_config('dacos_client')
        ...         ...
    """

    def __init__(
            self,
            agent_class: Type,
            name: Optional[str] = None,
            description: Optional[str] = None,
            tags: Optional[List[str]] = None,
            requires: Optional[List[str]] = None,  # 声明的依赖
            run_method: str = "run",  # Agent 的执行方法名
    ):
        self._agent_class = agent_class
        self._requires = requires or []
        self._run_method = run_method

        # 从类获取信息
        doc_description, _ = parse_docstring(agent_class.__doc__)

        self.name = name or self._infer_name_from_class(agent_class)
        self.description = description or doc_description or ""
        self.tags = tags or []

        super().__init__()

        # 缓存实例
        self._agent_instance: Optional[Any] = None

    def _infer_name_from_class(self, cls: Type) -> str:
        """从类名推断工具名"""
        name = cls.__name__
        for suffix in ('Agent', 'Tool', 'Handler'):
            if name.endswith(suffix):
                name = name[:-len(suffix)]
                break
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    def _build_schema(self) -> ToolSchema:
        """从 Agent 的 run 方法构建 Schema"""
        run_method = getattr(self._agent_class, self._run_method)
        sig = inspect.signature(run_method)
        hints = get_type_hints(run_method) if hasattr(run_method, '__annotations__') else {}
        _, param_descriptions = parse_docstring(run_method.__doc__)

        parameters = []
        for param_name, param in sig.parameters.items():
            if param_name in ('self', 'cls', 'kwargs'):
                continue

            param_type = hints.get(param_name, str)
            has_default = param.default is not inspect.Parameter.empty

            parameters.append(ToolParameter(
                name=param_name,
                type=get_json_type(param_type),
                description=param_descriptions.get(param_name, ""),
                required=not has_default,
                default=param.default if has_default else None,
            ))

        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=parameters,
            tags=self.tags,
        )

    async def run(self, **kwargs) -> ToolResult:
        """执行 Agent"""
        try:
            # 获取或创建 Agent 实例
            agent = self._get_or_create_agent()

            # 注入依赖
            self._inject_dependencies(agent)

            # 调用 Agent
            run_method = getattr(agent, self._run_method)
            result = await run_method(**kwargs)

            if isinstance(result, ToolResult):
                return result
            return ToolResult.ok(result)

        except Exception as e:
            logger.exception(f"AgentTool {self.name} execution failed")
            return ToolResult.fail(str(e))

    def _get_or_create_agent(self) -> Any:
        """获取或创建 Agent 实例"""
        if self._agent_instance is None:
            # 尝试创建实例
            # TODO: 这里需要与 alphora 框架的 Agent 创建机制对接
            self._agent_instance = self._agent_class()
        return self._agent_instance

    def _inject_dependencies(self, agent: Any) -> None:
        """注入依赖到 Agent"""
        if not self._config:
            return

        # 注入声明的依赖
        for dep_name in self._requires:
            value = self._config.get(dep_name)
            if value is not None and hasattr(agent, 'update_config'):
                agent.update_config(key=dep_name, value=value)


# ==================== @agent_tool 装饰器 ====================

def agent_tool(
        cls: Optional[Type] = None,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        requires: Optional[List[str]] = None,
        run_method: str = "run",
) -> Union[AgentTool, Callable[[Type], AgentTool]]:
    """
    Agent 工具装饰器

    将 Agent 类标记为可作为工具调用

    Examples:
        >>> @agent_tool(
        ...     name="data_query",
        ...     requires=['dacos_client', 'source_id']
        ... )
        ... class DataQueryAgent(BaseAgent):
        ...     '''数据查询智能体'''
        ...
        ...     async def run(self, query: str) -> ToolResult:
        ...         '''执行数据查询
        ...
        ...         Args:
        ...             query: 用户的数据查询问题
        ...         '''
        ...         client = self.get_config('dacos_client')
        ...         return ToolResult.ok({"sql": "...", "data": [...]})
    """
    def decorator(agent_cls: Type) -> AgentTool:
        return AgentTool(
            agent_class=agent_cls,
            name=name,
            description=description,
            tags=tags,
            requires=requires,
            run_method=run_method,
        )

    if cls is not None:
        return decorator(cls)
    return decorator


# ==================== 工具集 ====================

class ToolSet:
    """
    工具集合

    用于组织相关工具，支持命名空间

    Examples:
        >>> data_tools = ToolSet("data", "数据处理工具")
        >>>
        >>> @data_tools.tool
        ... def query(sql: str) -> dict:
        ...     '''执行查询'''
        ...     return execute(sql)
        >>>
        >>> @data_tools.tool
        ... def visualize(data: dict) -> str:
        ...     '''可视化数据'''
        ...     return generate_chart(data)
    """

    def __init__(
            self,
            namespace: str = "",
            description: str = "",
            tags: Optional[List[str]] = None,
    ):
        self.namespace = namespace
        self.description = description
        self.default_tags = tags or []
        self._tools: Dict[str, Tool] = {}

    def tool(
            self,
            func: Optional[F] = None,
            *,
            name: Optional[str] = None,
            description: Optional[str] = None,
            tags: Optional[List[str]] = None,
    ) -> Union[FunctionTool, Callable[[F], FunctionTool]]:
        """注册工具到此集合"""

        def decorator(fn: F) -> FunctionTool:
            tool_name = name or fn.__name__
            if self.namespace:
                full_name = f"{self.namespace}.{tool_name}"
            else:
                full_name = tool_name

            tool_instance = FunctionTool(
                func=fn,
                name=full_name,
                description=description,
                tags=(tags or []) + self.default_tags,
            )

            self._tools[full_name] = tool_instance
            return tool_instance

        if func is not None:
            return decorator(func)
        return decorator

    def add(self, t: Tool) -> Tool:
        """添加已有工具"""
        if self.namespace:
            t.name = f"{self.namespace}.{t.name}"
        t.tags = list(set(t.tags + self.default_tags))
        self._tools[t.name] = t
        return t

    @property
    def tools(self) -> List[Tool]:
        """获取所有工具"""
        return list(self._tools.values())

    def get(self, name: str) -> Optional[Tool]:
        """获取工具"""
        if name in self._tools:
            return self._tools[name]
        if self.namespace:
            full_name = f"{self.namespace}.{name}"
            return self._tools.get(full_name)
        return None

    def to_openai(self) -> List[Dict[str, Any]]:
        return [t.to_openai() for t in self._tools.values()]

    def to_anthropic(self) -> List[Dict[str, Any]]:
        return [t.to_anthropic() for t in self._tools.values()]

    def __iter__(self):
        return iter(self._tools.values())

    def __len__(self):
        return len(self._tools)


# ==================== 快捷创建 ====================

def create_tool(
        name: str,
        description: str,
        func: Callable,
        **kwargs
) -> FunctionTool:
    """快速创建工具"""
    return FunctionTool(func=func, name=name, description=description, **kwargs)