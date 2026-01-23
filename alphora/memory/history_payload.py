"""
历史记录载荷

定义 MemoryManager.build_history() 的返回数据结构。
这是一个受保护的数据结构，只能由 MemoryManager 创建，
BasePrompt 会验证其有效性后才会使用。

设计原则:
1. 不可变性：创建后不应被修改
2. 可验证性：包含验证标志，防止伪造
3. 工具链完整性：确保 tool_calls 和 tool 消息的对应关系
"""

from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
import time
import hashlib
import json


class ToolChainError(Exception):
    """工具调用链错误"""
    pass


class ToolChainValidator:
    """
    工具调用链验证器

    确保历史记录中的工具调用关系完整：
    - 每个 assistant 消息的 tool_calls 必须有对应的 tool 消息
    - 每个 tool 消息必须有对应的 assistant tool_call
    """

    @staticmethod
    def validate(messages: List[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
        """
        验证消息列表中的工具调用链完整性

        Args:
            messages: OpenAI 格式的消息列表

        Returns:
            (is_valid, error_message) - 验证结果和错误信息
        """
        # 收集所有 tool_call_ids (来自 assistant 消息)
        expected_tool_ids: Set[str] = set()
        # 收集所有 tool 消息的 tool_call_id
        actual_tool_ids: Set[str] = set()

        pending_tool_calls: Dict[str, str] = {}  # tool_call_id -> tool_name

        for i, msg in enumerate(messages):
            role = msg.get("role")

            if role == "assistant":
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    for tc in tool_calls:
                        tc_id = tc.get("id")
                        tc_name = tc.get("function", {}).get("name", "unknown")
                        if tc_id:
                            expected_tool_ids.add(tc_id)
                            pending_tool_calls[tc_id] = tc_name

            elif role == "tool":
                tool_call_id = msg.get("tool_call_id")
                if tool_call_id:
                    actual_tool_ids.add(tool_call_id)
                    # 移除已匹配的
                    pending_tool_calls.pop(tool_call_id, None)
                else:
                    return False, f"Tool message at index {i} missing 'tool_call_id'"

        # 检查是否有未匹配的 tool_calls
        missing_results = expected_tool_ids - actual_tool_ids
        if missing_results:
            missing_info = [f"{tid}" for tid in missing_results]
            return False, f"Missing tool results for tool_call_ids: {missing_info}"

        # 检查是否有多余的 tool 消息
        orphan_tools = actual_tool_ids - expected_tool_ids
        if orphan_tools:
            return False, f"Orphan tool messages with tool_call_ids: {list(orphan_tools)}"

        return True, None

    @staticmethod
    def find_incomplete_tool_calls(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        找出所有未完成的工具调用（有 tool_call 但没有对应 tool 结果）

        Returns:
            未完成的 tool_call 列表
        """
        expected: Dict[str, Dict] = {}  # tool_call_id -> tool_call_info

        for msg in messages:
            if msg.get("role") == "assistant":
                for tc in msg.get("tool_calls", []):
                    tc_id = tc.get("id")
                    if tc_id:
                        expected[tc_id] = tc

            elif msg.get("role") == "tool":
                tc_id = msg.get("tool_call_id")
                expected.pop(tc_id, None)

        return list(expected.values())


@dataclass(frozen=True)
class HistoryPayload:
    """
    历史记录载荷 (不可变)

    这是 MemoryManager.build_history() 的专用返回类型。
    包含验证签名，BasePrompt 会验证其有效性。

    Attributes:
        messages: OpenAI 格式的消息列表
        session_id: 来源会话ID
        created_at: 创建时间戳
        message_count: 消息数量
        round_count: 对话轮数
        has_tool_calls: 是否包含工具调用
        tool_chain_valid: 工具调用链是否完整
        _signature: 内部验证签名 (防止伪造)
    """
    messages: Tuple[Dict[str, Any], ...]    # 使用 tuple 确保不可变
    session_id: str
    created_at: float
    message_count: int
    round_count: int
    has_tool_calls: bool
    tool_chain_valid: bool
    _signature: str = field(repr=False)

    # 类级别的密钥
    _SECRET_KEY: str = field(default="alphora_memory_v1", repr=False, compare=False)

    def __post_init__(self):
        """验证签名"""
        expected_sig = self._compute_signature()
        if self._signature != expected_sig:
            raise ValueError("Invalid HistoryPayload: signature mismatch (possible forgery)")

    def _compute_signature(self) -> str:
        """计算签名"""
        # 基于关键属性计算哈希
        data = f"{self.session_id}:{self.created_at}:{self.message_count}:{self._SECRET_KEY}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    @classmethod
    def create(
            cls,
            messages: List[Dict[str, Any]],
            session_id: str,
            round_count: int = 0,
            validate_tool_chain: bool = True
    ) -> "HistoryPayload":
        """
        工厂方法：创建 HistoryPayload (仅供 MemoryManager 使用)

        Args:
            messages: OpenAI 格式的消息列表
            session_id: 会话ID
            round_count: 对话轮数
            validate_tool_chain: 是否验证工具调用链

        Returns:
            HistoryPayload 实例

        Raises:
            ToolChainError: 如果工具调用链不完整
        """
        # 检查是否有工具调用
        has_tool_calls = any(
            msg.get("role") == "assistant" and msg.get("tool_calls")
            for msg in messages
        )

        # 验证工具调用链
        tool_chain_valid = True
        if validate_tool_chain and has_tool_calls:
            is_valid, error_msg = ToolChainValidator.validate(messages)
            if not is_valid:
                raise ToolChainError(f"Tool chain validation failed: {error_msg}")
            tool_chain_valid = is_valid

        created_at = time.time()
        message_count = len(messages)

        # 先计算签名
        temp_sig = hashlib.sha256(
            f"{session_id}:{created_at}:{message_count}:alphora_memory_v1".encode()
        ).hexdigest()[:16]

        return cls(
            messages=tuple(messages),  # 转为 tuple
            session_id=session_id,
            created_at=created_at,
            message_count=message_count,
            round_count=round_count,
            has_tool_calls=has_tool_calls,
            tool_chain_valid=tool_chain_valid,
            _signature=temp_sig
        )

    def to_list(self) -> List[Dict[str, Any]]:
        """转换为可变的消息列表"""
        return list(self.messages)

    def is_empty(self) -> bool:
        """是否为空"""
        return self.message_count == 0

    def __len__(self) -> int:
        return self.message_count

    def __bool__(self) -> bool:
        return self.message_count > 0

    def __iter__(self):
        return iter(self.messages)


def is_valid_history_payload(obj: Any) -> bool:
    """
    检查对象是否是有效的 HistoryPayload

    用于 BasePrompt 验证传入的 history 参数
    """
    if not isinstance(obj, HistoryPayload):
        return False

    try:
        # 尝试验证签名
        expected_sig = obj._compute_signature()
        return obj._signature == expected_sig
    except Exception:
        return False

