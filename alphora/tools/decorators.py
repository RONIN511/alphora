from typing import Optional, Callable, Type, Union
from pydantic import BaseModel
from .core import Tool


def tool(
        name: Union[str, Callable, None] = None,
        description: Optional[str] = None,
        args_schema: Optional[Type[BaseModel]] = None
):
    """
    装饰器：支持多种调用方式
    1. @tool
    2. @tool("my_tool")
    3. @tool(name="my_tool", description="...")
    """

    if callable(name):
        func = name
        # 这种情况下 name 是函数，所以真正的 name 是 None (让 Tool.from_function 去提取)
        return Tool.from_function(func=func)

    tool_name = name  # 避免变量名混淆

    def _decorator(func: Callable) -> Tool:
        return Tool.from_function(
            func=func,
            name=tool_name,
            description=description,
            args_schema=args_schema
        )
    return _decorator

