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

    async def execute(
            self,
            tool_calls: Union[ToolCall, List[Dict[str, Any]]],
            memory_manager: Optional[Any] = None,
            memory_id: str = "default",
    ) -> List[Dict[str, Any]]:
        """
        全自动执行工具

        功能：
        1. 自动补全历史：如果记忆里没有这条 ToolCall 记录，自动伪造一条 Assistant 消息存进去
        2. 自动执行：并行运行所有工具。
        3. 自动存档：把运行结果存回记忆。

        Args:
            :param memory_id:
            :param tool_calls:
            :param memory_manager:
        """
        if not tool_calls:
            return []

        # 1. 规范化输入
        normalized_calls = []
        calls_list = tool_calls if isinstance(tool_calls, list) else [tool_calls]
        for call in calls_list:
            normalized_calls.append(call)

        # 自动补全 Input (Assistant Message)
        if memory_manager:
            self._ensure_assistant_entry(
                memory_manager,
                memory_id,
                normalized_calls,
            )

        # 并行执行 (Execution)
        tasks = [self._execute_single_tool(call) for call in normalized_calls]
        results_objects: List[ToolExecutionResult] = await asyncio.gather(*tasks)

        results_messages = [res.to_openai_message() for res in results_objects]

        #  自动保存 Output (Tool Message)
        if memory_manager:
            self._auto_save_results(memory_manager, memory_id, results_messages)

        return results_messages

    def _ensure_assistant_entry(
            self,
            memory_manager: Any,
            memory_id: str,
            tool_calls: List[Dict[str, Any]],

    ):
        """检查记忆完整性，如果缺 Assistant 记录，直接自动补全。"""
        # 1. 检查是否已经存在 (避免重复存储)
        # 获取最近几条记忆来比对 ID
        recent_memories = memory_manager.get_memories(memory_id)[-5:]
        existing_ids = set()
        for mem in recent_memories:
            payload = mem.content
            if isinstance(payload, dict) and "tool_calls" in payload:
                for tc in payload["tool_calls"]:
                    if "id" in tc:
                        existing_ids.add(tc["id"])

        # 检查当前这批 calls 是否都在记忆里了
        # 只要发现有一个 ID 没在记忆里，就认为这一整批都需要补全
        needs_save = False
        for call in tool_calls:
            if call.get("id") not in existing_ids:
                needs_save = True
                break

        if not needs_save:
            return    # 记忆是完美的，无需操作

        # 构造 Assistant 消息并保存
        logger.info(f"Auto-saving missing Assistant ToolCall entry to memory '{memory_id}'")

        assistant_payload = {
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls
        }

        memory_manager.add_payload(assistant_payload, memory_id=memory_id)

    def _auto_save_results(
            self,
            memory_manager: Any,
            memory_id: str,
            results: List[Dict[str, Any]]
    ):
        """自动写入结果"""
        for msg in results:
            memory_manager.add_payload(msg, memory_id=memory_id)

    async def _execute_single_tool(self, tool_call: Dict[str, Any]) -> ToolExecutionResult:
        """
        执行单个工具调用
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
            # 如果工具是 sync 的，arun 会自动在线程池运行，不会阻塞
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

