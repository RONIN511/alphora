"""
Alphora Memory Component (v2)

简洁、开发者友好的对话历史管理组件。

核心特性:
- 标准 OpenAI 消息格式 (user/assistant/tool/system)
- 完整的工具调用链路支持
- 灵活的历史构建与压缩
- 多种存储后端 (内存/JSON/SQLite)
- 撤销/重做支持
- 多会话管理

================================================================================
快速开始
================================================================================

```python
from alphora.memory import MemoryManager

# 创建管理器 (内存存储)
memory = MemoryManager()

# 或使用持久化存储
memory = MemoryManager(storage_path="./chat.db", storage_type="sqlite")
```

================================================================================
基本对话
================================================================================

```python
# 添加用户消息
memory.add_user("你好")

# 添加助手回复
memory.add_assistant("你好！有什么可以帮你的？")

# 获取历史用于 LLM 调用
messages = memory.build_messages(
    system_prompt="你是一个友好的助手。",
    user_query="今天天气怎么样？"
)
# 结果: [{"role": "system", ...}, {"role": "user", "content": "你好"}, ...]
```

================================================================================
工具调用
================================================================================

```python
# 用户请求
memory.add_user("帮我查一下北京天气")

# 助手决定调用工具
memory.add_assistant(
    content=None,  # 调用工具时 content 可以为空
    tool_calls=[{
        "id": "call_abc123",
        "type": "function",
        "function": {
            "name": "get_weather",
            "arguments": '{"city": "北京"}'
        }
    }]
)

# 工具执行结果
memory.add_tool_result(
    tool_call_id="call_abc123",
    name="get_weather",
    content='{"weather": "晴", "temp": 25}'
)

# 助手最终回复
memory.add_assistant("北京今天天气晴朗，温度25°C。")
```

================================================================================
历史管理
================================================================================

```python
# 删除最后一轮对话 (最后一个 user 及其后的所有消息)
memory.delete_last_round()

# 删除最后一轮工具调用 (assistant+tool_calls -> tools -> assistant)
memory.delete_last_tool_round()

# 压缩历史，保留最后 N 条
memory.compress(keep_last=20)

# 压缩历史，保留最后 N 轮
memory.compress(keep_rounds=5)

# 撤销上一步操作
memory.undo()

# 重做
memory.redo()

# 清空会话
memory.clear()
```

================================================================================
多会话支持
================================================================================

```python
# 使用不同的 session_id 管理多个对话
memory.add_user("你好", session_id="user_001")
memory.add_user("Hello", session_id="user_002")

# 获取指定会话的历史
messages = memory.build_messages(session_id="user_001")

# 列出所有会话
sessions = memory.list_sessions()

# 删除会话
memory.delete_session("user_001")
```

================================================================================
导出与持久化
================================================================================

```python
# 导出为 JSON
json_str = memory.export_session(format="json")

# 导出为 Markdown
md_str = memory.export_session(format="markdown")

# 保存到文件
memory.save_to_file("./chat_history.md", format="markdown")

# 导入会话
memory.import_session(json_str, session_id="restored")
```

================================================================================
与 BasePrompt 集成
================================================================================

```python
from alphora.memory import MemoryManager, HistoryBuilder

memory = MemoryManager()
builder = HistoryBuilder(memory)

# 链式构建
messages = (
    builder
    .with_system("你是一个助手")
    .with_history(max_rounds=10)
    .with_user("你好")
    .build()
)

# 或者一行搞定
messages = builder.quick_build(
    system="你是助手",
    user="帮我查天气",
    max_rounds=10
)
```

================================================================================
对话上下文管理器
================================================================================

```python
from alphora.memory import MemoryManager, ConversationContext

memory = MemoryManager()

# 使用上下文管理器自动管理消息
with ConversationContext(memory, session_id="user_001") as ctx:
    ctx.user("你好")

    messages = ctx.build_messages(system="你是助手")
    response = await llm.chat(messages)

    ctx.assistant(response.content)
# 退出时自动保存
```
"""

from alphora.memory.manager import MemoryManager
from alphora.memory.message import Message, MessageRole, ToolCall
from alphora.memory.history_builder import HistoryBuilder, ConversationContext

__all__ = [
    # 核心类
    "MemoryManager",
    "Message",
    "MessageRole",
    "ToolCall",

    # 辅助工具
    "HistoryBuilder",
    "ConversationContext",
]

