"""
Alphora Memory v2 使用示例

本文件展示了新版 Memory 组件的各种用法。
"""

import asyncio
import json


def example_basic_conversation():
    """
    示例1: 基本对话
    """
    print("\n" + "=" * 60)
    print("示例1: 基本对话")
    print("=" * 60)

    from alphora.memory import MemoryManager

    # 创建内存存储的管理器
    memory = MemoryManager()

    # 添加一轮对话
    memory.add_user("你好，我是小明")
    memory.add_assistant("你好小明！很高兴认识你，有什么可以帮助你的吗？")

    # 再来一轮
    memory.add_user("今天天气怎么样？")
    memory.add_assistant("很抱歉，我目前无法获取实时天气信息。你可以告诉我你所在的城市，我来帮你分析一下。")

    # 构建消息用于 LLM 调用
    messages = memory.build_messages(
        system_prompt="你是一个友好、乐于助人的AI助手。",
        user_query="我在北京"
    )

    print("构建的消息列表:")
    for msg in messages:
        role = msg["role"]
        content = msg.get("content", "")[:50]
        print(f"  [{role}]: {content}...")

    # 查看统计
    print("\n会话统计:")
    stats = memory.get_session_stats()
    print(f"  总消息数: {stats['total_messages']}")
    print(f"  对话轮数: {stats['rounds']}")


def example_tool_calling():
    """
    示例2: 工具调用完整链路
    """
    print("\n" + "=" * 60)
    print("示例2: 工具调用")
    print("=" * 60)

    from alphora.memory import MemoryManager

    memory = MemoryManager()

    # 用户请求
    memory.add_user("帮我查一下北京和上海的天气")

    # 助手决定调用工具 (可以并行调用多个)
    memory.add_assistant(
        content=None,  # 调用工具时 content 为 None
        tool_calls=[
            {
                "id": "call_weather_1",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": json.dumps({"city": "北京"})
                }
            },
            {
                "id": "call_weather_2",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": json.dumps({"city": "上海"})
                }
            }
        ]
    )

    # 工具执行结果 (按顺序添加)
    memory.add_tool_result(
        tool_call_id="call_weather_1",
        name="get_weather",
        content={"city": "北京", "weather": "晴", "temperature": 25, "humidity": 45}
    )

    memory.add_tool_result(
        tool_call_id="call_weather_2",
        name="get_weather",
        content={"city": "上海", "weather": "多云", "temperature": 28, "humidity": 65}
    )

    # 助手根据工具结果回复
    memory.add_assistant(
        "根据查询结果：\n"
        "- 北京：晴天，温度25°C，湿度45%\n"
        "- 上海：多云，温度28°C，湿度65%\n\n"
        "整体来看，北京更适合户外活动！"
    )

    # 查看完整的消息链
    print("完整消息链:")
    for msg in memory.get_messages():
        print(f"  [{msg.role}]: {msg.display_content[:60]}...")

    # 构建消息 (可以直接发给下一轮 LLM)
    messages = memory.build_messages(
        system_prompt="你是一个天气助手。"
    )
    print(f"\n构建了 {len(messages)} 条消息用于下一轮调用")


def example_history_management():
    """
    示例3: 历史管理
    """
    print("\n" + "=" * 60)
    print("示例3: 历史管理")
    print("=" * 60)

    from alphora.memory import MemoryManager

    memory = MemoryManager()

    # 添加多轮对话
    for i in range(5):
        memory.add_user(f"问题 {i+1}")
        memory.add_assistant(f"回答 {i+1}")

    print(f"初始消息数: {len(memory.get_messages())}")

    # 删除最后一轮
    deleted = memory.delete_last_round()
    print(f"删除最后一轮，移除了 {deleted} 条消息")
    print(f"当前消息数: {len(memory.get_messages())}")

    # 撤销
    if memory.undo():
        print("撤销成功！")
        print(f"当前消息数: {len(memory.get_messages())}")

    # 重做
    if memory.redo():
        print("重做成功！")
        print(f"当前消息数: {len(memory.get_messages())}")

    # 压缩历史
    removed, summary = memory.compress(keep_rounds=2)
    print(f"压缩历史，移除了 {removed} 条消息，保留最后2轮")
    print(f"当前消息数: {len(memory.get_messages())}")


def example_multi_session():
    """
    示例4: 多会话管理
    """
    print("\n" + "=" * 60)
    print("示例4: 多会话管理")
    print("=" * 60)

    from alphora.memory import MemoryManager

    memory = MemoryManager()

    # 同时管理多个用户的对话
    memory.add_user("我是用户A，你好", session_id="user_A")
    memory.add_assistant("你好用户A！", session_id="user_A")

    memory.add_user("我是用户B，Hello", session_id="user_B")
    memory.add_assistant("Hello User B!", session_id="user_B")

    memory.add_user("你能帮我做什么？", session_id="user_A")
    memory.add_assistant("我可以回答问题、帮你查询信息等。", session_id="user_A")

    # 列出所有会话
    print("所有会话:")
    for session_id in memory.list_sessions():
        stats = memory.get_session_stats(session_id)
        print(f"  {session_id}: {stats['total_messages']} 条消息, {stats['rounds']} 轮对话")

    # 分别构建各会话的消息
    print("\n用户A的历史:")
    for msg in memory.build_messages(session_id="user_A"):
        print(f"  [{msg['role']}]: {msg.get('content', '')[:40]}...")

    print("\n用户B的历史:")
    for msg in memory.build_messages(session_id="user_B"):
        print(f"  [{msg['role']}]: {msg.get('content', '')[:40]}...")


def example_export_import():
    """
    示例5: 导出与导入
    """
    print("\n" + "=" * 60)
    print("示例5: 导出与导入")
    print("=" * 60)

    from alphora.memory import MemoryManager

    memory = MemoryManager()

    # 添加一些对话
    memory.add_user("Python 怎么读取文件？")
    memory.add_assistant("在 Python 中，你可以使用 open() 函数读取文件...")

    # 导出为 JSON
    json_export = memory.export_session(format="json")
    print("JSON 导出:")
    print(json_export[:200] + "...")

    # 导出为 Markdown
    md_export = memory.export_session(format="markdown")
    print("\nMarkdown 导出:")
    print(md_export)

    # 在新管理器中导入
    memory2 = MemoryManager()
    count = memory2.import_session(json_export, session_id="imported")
    print(f"\n成功导入 {count} 条消息到新管理器")


def example_history_builder():
    """
    示例6: 使用 HistoryBuilder 链式构建
    """
    print("\n" + "=" * 60)
    print("示例6: HistoryBuilder 链式构建")
    print("=" * 60)

    from alphora.memory import MemoryManager, HistoryBuilder

    memory = MemoryManager()

    # 先添加一些历史
    memory.add_user("之前的问题1")
    memory.add_assistant("之前的回答1")
    memory.add_user("之前的问题2")
    memory.add_assistant("之前的回答2")

    # 使用 HistoryBuilder 链式构建
    builder = HistoryBuilder(memory)

    messages = (
        builder
        .with_system("你是一个专业的编程助手。")
        .with_system("请用简洁的语言回答问题。")
        .with_history(max_rounds=5)  # 包含历史
        .with_user("Python 的 list 和 tuple 有什么区别？")
        .build()
    )

    print("链式构建的消息:")
    for msg in messages:
        role = msg["role"]
        content = msg.get("content", "")[:50]
        print(f"  [{role}]: {content}...")

    # 或者使用 quick_build 一行搞定
    messages2 = builder.quick_build(
        system="你是助手",
        user="新的问题",
        max_rounds=3
    )
    print(f"\n快速构建: {len(messages2)} 条消息")


def example_persistent_storage():
    """
    示例7: 持久化存储
    """
    print("\n" + "=" * 60)
    print("示例7: 持久化存储")
    print("=" * 60)

    from alphora.memory import MemoryManager
    import tempfile
    import os

    # 使用临时文件演示
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        storage_path = f.name

    try:
        # 创建使用 JSON 存储的管理器
        memory1 = MemoryManager(
            storage_path=storage_path,
            storage_type="json"
        )

        # 添加对话
        memory1.add_user("这是持久化测试")
        memory1.add_assistant("消息将被保存到文件")

        print(f"保存到: {storage_path}")
        print(f"文件大小: {os.path.getsize(storage_path)} bytes")

        # 创建新的管理器，加载相同的存储
        memory2 = MemoryManager(
            storage_path=storage_path,
            storage_type="json"
        )

        print(f"\n从文件加载了 {len(memory2.get_messages())} 条消息:")
        for msg in memory2.get_messages():
            print(f"  [{msg.role}]: {msg.content}")

    finally:
        # 清理临时文件
        os.unlink(storage_path)


def example_auto_compress():
    """
    示例8: 自动压缩
    """
    print("\n" + "=" * 60)
    print("示例8: 自动压缩")
    print("=" * 60)

    from alphora.memory import MemoryManager

    # 设置最大消息数，超出时自动压缩
    memory = MemoryManager(max_messages=6)

    print("添加对话，当超过6条时会自动压缩...")

    for i in range(5):
        memory.add_user(f"问题 {i+1}")
        memory.add_assistant(f"回答 {i+1}")
        print(f"  添加第{i+1}轮后，消息数: {len(memory.get_messages())}")


async def example_conversation_context():
    """
    示例9: 对话上下文管理器
    """
    print("\n" + "=" * 60)
    print("示例9: 对话上下文管理器")
    print("=" * 60)

    from alphora.memory import MemoryManager, ConversationContext

    memory = MemoryManager()

    # 模拟异步 LLM 调用
    async def mock_llm_call(messages):
        await asyncio.sleep(0.1)  # 模拟网络延迟
        return "这是 AI 的回复"

    # 使用上下文管理器
    async with ConversationContext(memory, session_id="demo") as ctx:
        # 添加用户消息
        ctx.user("你好，请介绍一下自己")

        # 构建消息并调用 LLM
        messages = ctx.build_messages(system="你是一个友好的 AI 助手")
        response = await mock_llm_call(messages)

        # 添加助手回复
        ctx.assistant(response)

    # 退出上下文后，消息已自动保存
    print("会话内容 (自动保存):")
    for msg in memory.get_messages(session_id="demo"):
        print(f"  [{msg.role}]: {msg.content}")


def example_search():
    """
    示例10: 搜索消息
    """
    print("\n" + "=" * 60)
    print("示例10: 搜索消息")
    print("=" * 60)

    from alphora.memory import MemoryManager

    memory = MemoryManager()

    # 添加一些对话
    memory.add_user("Python 怎么读取 JSON 文件？")
    memory.add_assistant("可以使用 json.load() 函数...")
    memory.add_user("那怎么写入 JSON 呢？")
    memory.add_assistant("使用 json.dump() 函数...")
    memory.add_user("如何处理大型 CSV 文件？")
    memory.add_assistant("可以使用 pandas 库...")

    # 搜索包含 "JSON" 的消息
    results = memory.search("JSON")
    print("搜索 'JSON' 的结果:")
    for msg in results:
        print(f"  [{msg.role}]: {msg.content[:50]}...")

    # 只搜索用户消息
    results = memory.search("文件", role="user")
    print("\n搜索用户消息中的 '文件':")
    for msg in results:
        print(f"  [{msg.role}]: {msg.content}")


def main():
    """运行所有示例"""
    example_basic_conversation()
    example_tool_calling()
    example_history_management()
    example_multi_session()
    example_export_import()
    example_history_builder()
    example_persistent_storage()
    example_auto_compress()
    asyncio.run(example_conversation_context())
    example_search()

    print("\n" + "=" * 60)
    print("所有示例运行完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()