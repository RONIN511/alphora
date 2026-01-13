"""
alphora.tools.executor - 工具执行器

设计目标：
1. 统一的工具执行入口
2. 支持并行执行
3. 执行追踪和统计
4. LLM 响应解析
"""

from __future__ import annotations

import json
import asyncio
import logging
import uuid
import time
from typing import Any, Callable, Dict, List, Optional, Union, Awaitable
from dataclasses import dataclass, field
from datetime import datetime

from .types import ToolResult, ToolCall, ToolStatus, ToolConfig
from .tool import Tool

logger = logging.getLogger(__name__)


# ==================== 执行追踪 ====================

@dataclass
class ExecutionTrace:
    """单次执行的追踪信息"""
    call_id: str
    tool_name: str
    arguments: Dict[str, Any]
    result: Optional[ToolResult] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: float = 0.0
    error: Optional[str] = None
    retries: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "status": self.result.status.value if self.result else "pending",
            "duration_ms": self.duration_ms,
            "error": self.error,
            "retries": self.retries,
        }


@dataclass
class ExecutionTracer:
    """执行追踪器"""
    traces: List[ExecutionTrace] = field(default_factory=list)

    def add(self, trace: ExecutionTrace) -> None:
        self.traces.append(trace)

    def get_by_tool(self, tool_name: str) -> List[ExecutionTrace]:
        return [t for t in self.traces if t.tool_name == tool_name]

    def get_stats(self) -> Dict[str, Any]:
        if not self.traces:
            return {}

        success_count = sum(1 for t in self.traces if t.result and t.result.success)
        total_duration = sum(t.duration_ms for t in self.traces)

        return {
            "total_calls": len(self.traces),
            "success_count": success_count,
            "error_count": len(self.traces) - success_count,
            "total_duration_ms": total_duration,
            "avg_duration_ms": total_duration / len(self.traces),
        }

    def clear(self) -> None:
        self.traces.clear()


# ==================== 工具执行器 ====================

class ToolExecutor:
    """
    工具执行器

    统一的工具执行入口，支持：
    - 单工具执行
    - 批量执行
    - 并行执行
    - LLM 响应解析
    - 执行追踪

    Examples:
        >>> executor = ToolExecutor()
        >>> executor.register(search_tool)
        >>> executor.register(calc_tool)
        >>>
        >>> # 单工具执行
        >>> result = await executor.execute("search", query="Python")
        >>>
        >>> # 解析 LLM 响应并执行
        >>> calls = executor.parse_llm_response(response)
        >>> results = await executor.execute_calls(calls)
    """

    def __init__(
            self,
            tools: Optional[List[Tool]] = None,
            config: Optional[ToolConfig] = None,
    ):
        self._tools: Dict[str, Tool] = {}
        self._config = config or ToolConfig()
        self._tracer = ExecutionTracer()

        # 回调
        self._on_start: List[Callable] = []
        self._on_end: List[Callable] = []

        if tools:
            for t in tools:
                self.register(t)

    # ==================== 工具管理 ====================

    def register(self, tool: Tool) -> ToolExecutor:
        """注册工具"""
        if tool._config is None:
            tool.configure(self._config)
        self._tools[tool.name] = tool
        return self

    def unregister(self, name: str) -> bool:
        """注销工具"""
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get(self, name: str) -> Optional[Tool]:
        """获取工具"""
        return self._tools.get(name)

    def list(self) -> List[Tool]:
        """列出所有工具"""
        return list(self._tools.values())

    def names(self) -> List[str]:
        """列出所有工具名"""
        return list(self._tools.keys())

    # ==================== 执行 ====================

    async def execute(self, name: str, **kwargs) -> ToolResult:
        """执行单个工具"""
        tool = self._tools.get(name)
        if not tool:
            return ToolResult.fail(f"Tool not found: {name}")

        call = ToolCall(
            id=str(uuid.uuid4()),
            name=name,
            arguments=kwargs,
        )

        return await self._execute_call(tool, call)

    async def execute_call(self, call: ToolCall) -> ToolResult:
        """执行 ToolCall"""
        tool = self._tools.get(call.name)
        if not tool:
            return ToolResult.fail(f"Tool not found: {call.name}")

        return await self._execute_call(tool, call)

    async def execute_calls(self, calls: List[ToolCall]) -> List[ToolResult]:
        """顺序执行多个调用"""
        results = []
        for call in calls:
            result = await self.execute_call(call)
            results.append(result)
        return results

    async def execute_parallel(
            self,
            calls: List[ToolCall],
            max_concurrent: int = 5,
    ) -> List[ToolResult]:
        """并行执行多个调用"""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def execute_with_semaphore(call: ToolCall) -> ToolResult:
            async with semaphore:
                return await self.execute_call(call)

        tasks = [execute_with_semaphore(call) for call in calls]
        return await asyncio.gather(*tasks)

    async def _execute_call(self, tool: Tool, call: ToolCall) -> ToolResult:
        """执行工具调用（内部方法）"""
        trace = ExecutionTrace(
            call_id=call.id,
            tool_name=call.name,
            arguments=call.arguments,
            started_at=datetime.now(),
        )

        # 触发开始回调
        for callback in self._on_start:
            try:
                callback(call)
            except Exception as e:
                logger.warning(f"on_start callback error: {e}")

        start_time = time.time()

        try:
            # 执行工具
            result = await tool(**call.arguments)

            # 设置追踪信息
            result.tool_name = call.name
            result.call_id = call.id
            result.started_at = trace.started_at
            result.finished_at = datetime.now()
            result.duration_ms = (time.time() - start_time) * 1000

            trace.result = result
            trace.duration_ms = result.duration_ms

        except Exception as e:
            logger.exception(f"Tool execution error: {call.name}")
            result = ToolResult.fail(str(e))
            result.tool_name = call.name
            result.call_id = call.id

            trace.result = result
            trace.error = str(e)
            trace.duration_ms = (time.time() - start_time) * 1000

        trace.finished_at = datetime.now()
        self._tracer.add(trace)

        # 触发结束回调
        for callback in self._on_end:
            try:
                callback(trace)
            except Exception as e:
                logger.warning(f"on_end callback error: {e}")

        return result

    # ==================== LLM 响应解析 ====================

    def parse_llm_response(self, response: Any) -> List[ToolCall]:
        """
        解析 LLM 响应，提取工具调用

        支持 OpenAI 和 Anthropic 格式
        """
        calls = []

        # OpenAI 格式
        if hasattr(response, 'choices'):
            message = response.choices[0].message
            if hasattr(message, 'tool_calls') and message.tool_calls:
                for tc in message.tool_calls:
                    calls.append(ToolCall.from_openai(tc))
            return calls

        # Anthropic 格式
        if hasattr(response, 'content'):
            for block in response.content:
                if hasattr(block, 'type') and block.type == 'tool_use':
                    calls.append(ToolCall.from_anthropic(block))
            return calls

        # 字典格式（OpenAI）
        if isinstance(response, dict):
            if 'choices' in response:
                message = response['choices'][0].get('message', {})
                tool_calls = message.get('tool_calls', [])
                for tc in tool_calls:
                    calls.append(ToolCall.from_openai(tc))
                return calls

            # 直接的工具调用格式
            if 'tool_calls' in response:
                for tc in response['tool_calls']:
                    calls.append(ToolCall.from_openai(tc))
                return calls

        # 列表格式（多个工具调用）
        if isinstance(response, list):
            for item in response:
                if isinstance(item, dict) and 'name' in item:
                    calls.append(ToolCall.from_dict(item))

        return calls

    def build_tool_messages(
            self,
            results: List[ToolResult],
            format: str = "openai",
    ) -> List[Dict[str, Any]]:
        """
        构建工具结果消息

        用于将工具执行结果发送回 LLM
        """
        messages = []

        for result in results:
            if format == "openai":
                messages.append({
                    "role": "tool",
                    "tool_call_id": result.call_id or "",
                    "content": result.to_llm_content(),
                })
            elif format == "anthropic":
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": result.call_id or "",
                        "content": result.to_llm_content(),
                    }]
                })

        return messages

    # ==================== Schema 生成 ====================

    def get_tools_schema(self, format: str = "openai") -> List[Dict[str, Any]]:
        """获取所有工具的 Schema"""
        if format == "openai":
            return [t.to_openai() for t in self._tools.values()]
        elif format == "anthropic":
            return [t.to_anthropic() for t in self._tools.values()]
        else:
            raise ValueError(f"Unsupported format: {format}")

    # ==================== 回调注册 ====================

    def on_start(self, callback: Callable[[ToolCall], None]) -> ToolExecutor:
        """注册执行开始回调"""
        self._on_start.append(callback)
        return self

    def on_end(self, callback: Callable[[ExecutionTrace], None]) -> ToolExecutor:
        """注册执行结束回调"""
        self._on_end.append(callback)
        return self

    # ==================== 追踪和统计 ====================

    @property
    def tracer(self) -> ExecutionTracer:
        return self._tracer

    def get_stats(self) -> Dict[str, Any]:
        return self._tracer.get_stats()

    def clear_traces(self) -> None:
        self._tracer.clear()


# ==================== 带工具的对话执行器 ====================

class ToolConversationExecutor:
    """
    带工具的对话执行器

    自动处理工具调用循环

    Examples:
        >>> executor = ToolConversationExecutor(llm, tools)
        >>> response = await executor.chat("查询今年销售额最高的产品")
    """

    def __init__(
            self,
            llm: Any,
            tools: List[Tool],
            system_prompt: Optional[str] = None,
            max_iterations: int = 10,
            format: str = "openai",
    ):
        self.llm = llm
        self.tool_executor = ToolExecutor(tools)
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        self.format = format

    async def chat(
            self,
            message: str,
            history: Optional[List[Dict]] = None,
    ) -> str:
        """
        执行带工具的对话

        自动处理工具调用循环，直到 LLM 返回最终回复
        """
        # 构建消息
        messages = history or []
        if self.system_prompt and not any(m.get('role') == 'system' for m in messages):
            messages.insert(0, {"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": message})

        # 获取工具定义
        tools_schema = self.tool_executor.get_tools_schema(self.format)

        for iteration in range(self.max_iterations):
            # 调用 LLM
            response = await self.llm.chat(
                messages=messages,
                tools=tools_schema if tools_schema else None,
            )

            # 解析工具调用
            tool_calls = self.tool_executor.parse_llm_response(response)

            if not tool_calls:
                # 没有工具调用，返回最终回复
                return self._extract_response_text(response)

            # 添加 assistant 消息
            messages.append(self._build_assistant_message(response))

            # 执行工具
            results = await self.tool_executor.execute_calls(tool_calls)

            # 添加工具结果
            tool_messages = self.tool_executor.build_tool_messages(results, self.format)
            messages.extend(tool_messages)

            logger.debug(f"Iteration {iteration + 1}: executed {len(tool_calls)} tools")

        return "达到最大迭代次数，无法完成任务"

    def _extract_response_text(self, response: Any) -> str:
        """提取响应文本"""
        if self.format == "anthropic":
            if hasattr(response, 'content'):
                return "".join(
                    block.text for block in response.content
                    if hasattr(block, 'text')
                )

        if hasattr(response, 'choices'):
            return response.choices[0].message.content or ""

        if isinstance(response, dict):
            return response.get('content', response.get('text', str(response)))

        return str(response)

    def _build_assistant_message(self, response: Any) -> Dict[str, Any]:
        """构建 assistant 消息"""
        if self.format == "anthropic":
            return {"role": "assistant", "content": response.content}

        if hasattr(response, 'choices'):
            msg = response.choices[0].message
            result = {"role": "assistant", "content": msg.content}

            if msg.tool_calls:
                result["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    for tc in msg.tool_calls
                ]

            return result

        return {"role": "assistant", "content": str(response)}

