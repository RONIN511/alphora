import json
import asyncio
import logging
from typing import List, Dict, Any, Union, Optional
from pydantic import BaseModel

from .core import Tool
from .registry import ToolRegistry
from .exceptions import ToolValidationError, ToolExecutionError
from alphora.models.llms.types import ToolCall

# 设置日志
logger = logging.getLogger(__name__)


class ToolExecutionResult(BaseModel):
    """
    单个工具执行的标准化结果。
    """
    tool_call_id: str          # 对应 OpenAI 的 call_id，必须原样返回
    tool_name: str             # 工具名称
    content: str               # 执行结果（被序列化为字符串）
    status: str = "success"    # 状态: "success" | "error"
    error_type: Optional[str] = None # 如果出错，记录错误类型

    def to_openai_message(self) -> dict:
        """
        转换为 OpenAI 聊天消息格式 (role='tool')
        """
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "name": self.tool_name,
            "content": self.content
        }


class ToolExecutor:
    """
    智能体工具执行引擎。
    负责解析大模型指令、并行调度工具、捕获异常并生成反馈。
    """
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def execute(self, tool_calls: ToolCall | Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        主入口：接收大模型的 tool_calls 列表，并行执行，返回结果列表。

        Args:
            tool_calls: OpenAI SDK 返回的 tool_calls 对象列表 (或是字典形式)。

        Returns:
            List[Dict]: 符合 OpenAI 格式的 message 列表。
        """
        if not tool_calls:
            return []

        tasks = []
        for call in tool_calls:
            call_data = call if isinstance(call, dict) else call.model_dump()
            tasks.append(self._execute_single_tool(call_data))

        # 并行执行所有工具调用 (Fail-safe: return_exceptions=False, 因为我们在内部已经捕获了所有异常，这里不会抛出)
        results: List[ToolExecutionResult] = await asyncio.gather(*tasks)

        return [res.to_openai_message() for res in results]

    async def _execute_single_tool(self, tool_call: Dict[str, Any]) -> ToolExecutionResult:
        """
        执行单个工具调用，包含完整的错误边界处理。
        """
        call_id = tool_call.get("id")
        function_data = tool_call.get("function", {})
        tool_name = function_data.get("name")
        arguments_str = function_data.get("arguments", "{}")

        logger.info(f"Executing tool: {tool_name} [id={call_id}]")

        try:
            # 1. 查找工具
            tool = self.registry.get_tool(tool_name)
            if not tool:
                return ToolExecutionResult(
                    tool_call_id=call_id,
                    tool_name=tool_name,
                    content=f"Error: Tool '{tool_name}' not found.",
                    status="error",
                    error_type="ToolNotFoundError"
                )

            # 2. 解析 JSON 参数
            try:
                if isinstance(arguments_str, str):
                    arguments = json.loads(arguments_str)
                else:
                    arguments = arguments_str # 容错：有些模型可能直接返回dict
            except json.JSONDecodeError as e:
                return ToolExecutionResult(
                    tool_call_id=call_id,
                    tool_name=tool_name,
                    content=f"Error: Invalid JSON arguments. {str(e)}",
                    status="error",
                    error_type="JSONDecodeError"
                )

            # 3. 执行工具 (Tool.arun 内部处理了 Pydantic 验证和 Sync/Async 桥接)
            # 注意：如果工具是 sync 的，arun 会自动在线程池运行，不会阻塞
            result_data = await tool.arun(**arguments)

            # 4. 序列化结果
            # 如果结果不是字符串，尝试转为 JSON 字符串
            if not isinstance(result_data, str):
                content = json.dumps(result_data, ensure_ascii=False)
            else:
                content = result_data

            return ToolExecutionResult(
                tool_call_id=call_id,
                tool_name=tool_name,
                content=content,
                status="success"
            )

        # === 错误反馈闭环 ===
        # 捕获已知错误，返回给大模型让其修正
        except ToolValidationError as e:
            logger.warning(f"Validation failed for {tool_name}: {e}")
            return ToolExecutionResult(
                tool_call_id=call_id,
                tool_name=tool_name,
                content=f"Error: Arguments validation failed. {str(e)}",
                status="error",
                error_type="ValidationError"
            )

        except ToolExecutionError as e:
            logger.error(f"Runtime error in {tool_name}: {e}")
            return ToolExecutionResult(
                tool_call_id=call_id,
                tool_name=tool_name,
                content=f"Error: Execution failed. {str(e)}",
                status="error",
                error_type="ExecutionError"
            )

        except Exception as e:
            # 捕获所有未预料的系统级错误 (兜底)
            logger.exception(f"Unexpected error in {tool_name}")
            return ToolExecutionResult(
                tool_call_id=call_id,
                tool_name=tool_name,
                content=f"Error: An unexpected internal error occurred. {str(e)}",
                status="error",
                error_type="InternalError"
            )

