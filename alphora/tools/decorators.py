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

