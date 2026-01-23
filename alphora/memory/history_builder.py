"""
历史构建器

用于快速构建发送给 LLM 的消息列表，并与 BasePrompt 集成。

使用示例:
```python
from alphora.memory import MemoryManager, HistoryBuilder

memory = MemoryManager()
builder = HistoryBuilder(memory)

# 快速构建消息
messages = (
    builder
    .with_system("你是一个友好的助手")
    .with_history(max_rounds=5)
    .with_user("你好")
    .build()
)

# 或者一行搞定
messages = builder.quick_build(
    system="你是一个助手",
    user="帮我查天气",
    max_rounds=10
)
```
"""

from typing import Any, Dict, List, Optional, Union
from alphora.memory.message import Message, ToolCall


class HistoryBuilder:
    """
    链式消息构建器

    提供流式 API 构建发送给 LLM 的消息列表。
    """

    def __init__(self, memory: "MemoryManager", session_id: str = "default"):
        """
        Args:
            memory: MemoryManager 实例
            session_id: 默认会话ID
        """
        self.memory = memory
        self.session_id = session_id
        self._messages: List[Dict[str, Any]] = []
        self._include_history = False
        self._history_config = {}

    def reset(self) -> "HistoryBuilder":
        """重置构建器"""
        self._messages = []
        self._include_history = False
        self._history_config = {}
        return self

    def with_system(self, content: Union[str, List[str]]) -> "HistoryBuilder":
        """
        添加系统消息

        Args:
            content: 系统提示词 (支持字符串或字符串列表)
        """
        if isinstance(content, str):
            self._messages.append({"role": "system", "content": content})
        else:
            for c in content:
                self._messages.append({"role": "system", "content": c})
        return self

    def with_history(
            self,
            max_rounds: Optional[int] = None,
            max_messages: Optional[int] = None,
            include_system: bool = False,
            session_id: Optional[str] = None
    ) -> "HistoryBuilder":
        """
        添加历史记录

        Args:
            max_rounds: 最大对话轮数
            max_messages: 最大消息数
            include_system: 是否包含历史中的 system 消息
            session_id: 指定会话ID (不传使用默认)
        """
        self._include_history = True
        self._history_config = {
            "max_rounds": max_rounds,
            "max_messages": max_messages,
            "include_system": include_system,
            "session_id": session_id or self.session_id,
        }
        return self

    def with_user(self, content: str) -> "HistoryBuilder":
        """
        添加用户消息

        Args:
            content: 用户输入
        """
        self._messages.append({"role": "user", "content": content})
        return self

    def with_assistant(
            self,
            content: Optional[str] = None,
            tool_calls: Optional[List[Dict]] = None
    ) -> "HistoryBuilder":
        """
        添加助手消息

        Args:
            content: 助手回复
            tool_calls: 工具调用
        """
        msg = {"role": "assistant"}
        if content is not None:
            msg["content"] = content
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self._messages.append(msg)
        return self

    def with_tool(
            self,
            tool_call_id: str,
            content: str,
            name: Optional[str] = None
    ) -> "HistoryBuilder":
        """
        添加工具结果消息

        Args:
            tool_call_id: 工具调用ID
            content: 执行结果
            name: 工具名称
        """
        msg = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content
        }
        if name:
            msg["name"] = name
        self._messages.append(msg)
        return self

    def with_messages(self, messages: List[Dict[str, Any]]) -> "HistoryBuilder":
        """
        添加原始消息列表

        Args:
            messages: OpenAI 格式的消息列表
        """
        self._messages.extend(messages)
        return self

    def build(self) -> List[Dict[str, Any]]:
        """
        构建最终的消息列表

        Returns:
            OpenAI 格式的消息列表
        """
        result = []
        history_inserted = False

        for msg in self._messages:
            # 在第一个 user 消息之前插入历史
            if msg["role"] == "user" and not history_inserted and self._include_history:
                history = self.memory._get_history_for_build(
                    session_id=self._history_config.get("session_id", self.session_id),
                    max_rounds=self._history_config.get("max_rounds"),
                    max_messages=self._history_config.get("max_messages"),
                    include_system=self._history_config.get("include_system", False),
                )
                result.extend(history)
                history_inserted = True

            result.append(msg)

        # 如果没有 user 消息，历史还是要加
        if self._include_history and not history_inserted:
            history = self.memory._get_history_for_build(
                session_id=self._history_config.get("session_id", self.session_id),
                **{k: v for k, v in self._history_config.items() if k != "session_id"}
            )
            result.extend(history)

        return result

    def quick_build(
            self,
            system: Optional[Union[str, List[str]]] = None,
            user: Optional[str] = None,
            max_rounds: Optional[int] = None,
            max_messages: Optional[int] = None,
            session_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        快速构建消息（一行搞定）

        Args:
            system: 系统提示词
            user: 用户输入
            max_rounds: 最大历史轮数
            max_messages: 最大历史消息数
            session_id: 会话ID

        Returns:
            OpenAI 格式的消息列表

        Example:
            messages = builder.quick_build(
                system="你是助手",
                user="你好",
                max_rounds=10
            )
        """
        self.reset()

        if system:
            self.with_system(system)

        # 自动添加历史
        self.with_history(
            max_rounds=max_rounds,
            max_messages=max_messages,
            session_id=session_id
        )

        if user:
            self.with_user(user)

        return self.build()


class ConversationContext:
    """
    对话上下文管理器

    用于在多轮对话中自动管理消息的添加和历史构建。

    使用示例:
    ```python
    memory = MemoryManager()

    async with ConversationContext(memory, session_id="user_001") as ctx:
        # 自动添加用户消息
        ctx.user("你好")

        # 构建消息调用 LLM
        messages = ctx.build_messages(system="你是助手")
        response = await llm.chat(messages)

        # 自动添加助手回复
        ctx.assistant(response.content)
    ```
    """

    def __init__(
            self,
            memory: "MemoryManager",
            session_id: str = "default",
            max_rounds: Optional[int] = None,
            auto_save: bool = True
    ):
        """
        Args:
            memory: MemoryManager 实例
            session_id: 会话ID
            max_rounds: 构建历史时的最大轮数
            auto_save: 是否自动保存到历史
        """
        self.memory = memory
        self.session_id = session_id
        self.max_rounds = max_rounds
        self.auto_save = auto_save

        self._pending_messages: List[Dict[str, Any]] = []

    def user(self, content: str, save: Optional[bool] = None) -> "ConversationContext":
        """
        添加用户消息

        Args:
            content: 用户输入
            save: 是否保存到历史 (默认使用 auto_save 设置)
        """
        if save is None:
            save = self.auto_save

        if save:
            self.memory.add_user(content, session_id=self.session_id)
        else:
            self._pending_messages.append({"role": "user", "content": content})

        return self

    def assistant(
            self,
            content: Optional[str] = None,
            tool_calls: Optional[List[Dict]] = None,
            save: Optional[bool] = None
    ) -> "ConversationContext":
        """
        添加助手消息

        Args:
            content: 助手回复
            tool_calls: 工具调用
            save: 是否保存到历史
        """
        if save is None:
            save = self.auto_save

        if save:
            self.memory.add_assistant(content, tool_calls, session_id=self.session_id)
        else:
            msg = {"role": "assistant"}
            if content is not None:
                msg["content"] = content
            if tool_calls:
                msg["tool_calls"] = tool_calls
            self._pending_messages.append(msg)

        return self

    def tool_result(
            self,
            tool_call_id: str,
            name: str,
            content: str,
            save: Optional[bool] = None
    ) -> "ConversationContext":
        """
        添加工具结果

        Args:
            tool_call_id: 工具调用ID
            name: 工具名称
            content: 执行结果
            save: 是否保存到历史
        """
        if save is None:
            save = self.auto_save

        if save:
            self.memory.add_tool_result(tool_call_id, name, content, session_id=self.session_id)
        else:
            self._pending_messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": name,
                "content": content
            })

        return self

    def build_messages(
            self,
            system: Optional[Union[str, List[str]]] = None,
            include_pending: bool = True
    ) -> List[Dict[str, Any]]:
        """
        构建消息列表

        Args:
            system: 系统提示词
            include_pending: 是否包含待保存的消息

        Returns:
            OpenAI 格式的消息列表
        """
        messages = self.memory.build_messages(
            session_id=self.session_id,
            system_prompt=system,
            max_rounds=self.max_rounds,
        )

        if include_pending:
            messages.extend(self._pending_messages)

        return messages

    def save_pending(self):
        """保存所有待保存的消息到历史"""
        for msg in self._pending_messages:
            self.memory.add_message(msg, session_id=self.session_id)
        self._pending_messages.clear()

    def discard_pending(self):
        """丢弃所有待保存的消息"""
        self._pending_messages.clear()

    def __enter__(self) -> "ConversationContext":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # 如果没有异常，保存待保存的消息
        if exc_type is None:
            self.save_pending()

    async def __aenter__(self) -> "ConversationContext":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.save_pending()