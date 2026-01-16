import threading
from typing import Dict, List, Optional, Callable, Union, Any
from .core import Tool
from .exceptions import ToolRegistrationError


class ToolRegistry:
    """
    工具注册中心。
    负责管理所有的 Tool 实例，处理命名冲突，并生成聚合的 OpenAI Tools Schema。
    """
    def __init__(self):
        # 使用字典存储，key=tool_name
        self._tools: Dict[str, Tool] = {}
        # 简单的线程锁，防止并发注册时的竞争条件（虽然 Python GIL 存在，但在 web 框架启动时通常是单线程，加上是个好习惯）
        self._lock = threading.RLock()

    def register(
            self,
            tool_or_func: Union[Tool, Callable],
            name_override: Optional[str] = None
    ) -> Tool:
        """
        核心注册方法。

        Args:
            tool_or_func: 可以是一个已经封装好的 Tool 对象，也可以是一个原生函数/方法。
            name_override: 强制重命名工具（用于解决重名问题）。
        """
        with self._lock:
            # 1. 统一转换为 Tool 对象
            if isinstance(tool_or_func, Tool):
                tool = tool_or_func
                # 如果提供了重命名，创建一个副本
                if name_override and name_override != tool.name:
                    tool = tool.model_copy(update={"name": name_override})
            elif callable(tool_or_func):
                # 如果是函数或方法，使用工厂方法创建
                tool = Tool.from_function(tool_or_func, name=name_override)
            else:
                raise ToolRegistrationError(f"Invalid item type: {type(tool_or_func)}. Must be Tool or Callable.")

            # 2. 检查命名冲突
            if tool.name in self._tools:
                # 策略：严格报错。不建议自动加后缀，这会导致大模型调用不可预测。
                # 开发者必须显式使用 name_override 解决冲突。
                raise ToolRegistrationError(
                    f"Tool with name '{tool.name}' already registered. "
                    "Please provide a unique 'name_override' or rename the function."
                )

            # 3. 入库
            self._tools[tool.name] = tool
            return tool

    def get_tool(self, name: str) -> Optional[Tool]:
        """获取指定工具"""
        return self._tools.get(name)

    def get_all_tools(self) -> List[Tool]:
        return list(self._tools.values())

    def get_openai_tools_schema(self) -> List[Dict[str, Any]]:
        """
        一次性获取所有注册工具的 Schema，直接喂给 client.chat.completions.create
        """
        return [tool.openai_schema for tool in self._tools.values()]

    def clear(self):
        with self._lock:
            self._tools.clear()

# 全局可选的默认注册表（便于简单脚本使用）
default_registry = ToolRegistry()
