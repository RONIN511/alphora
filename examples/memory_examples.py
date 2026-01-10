"""
Alphora Storage & Memory 组件使用示例

展示如何使用新的Storage和Memory组件
"""

import asyncio


# ==================== Storage 组件示例 ====================

def storage_examples():
    """Storage组件使用示例"""
    print("=" * 60)
    print("Storage Component Examples")
    print("=" * 60)
    
    from alphora.storage import JSONStorage, SQLiteStorage, InMemoryStorage, create_storage
    
    # 1. 内存存储（适合测试）
    print("\n1. InMemoryStorage（内存存储）")
    storage = InMemoryStorage()
    storage.set("config", {"theme": "dark", "language": "zh"})
    print(f"   Config: {storage.get('config')}")
    
    # 2. JSON存储（适合开发）
    print("\n2. JSONStorage（JSON文件存储）")
    storage = JSONStorage("./data/app_storage.json")
    
    # 键值操作
    storage.set("user:1:name", "张三")
    storage.set("user:1:age", 25)
    print(f"   User name: {storage.get('user:1:name')}")
    
    # 列表操作（适合存储历史记录）
    storage.rpush("user:1:history", "登录", "浏览商品", "下单")
    print(f"   History: {storage.lrange('user:1:history', 0, -1)}")
    
    # 哈希操作（适合存储结构化数据）
    storage.hset("product:1", "name", "iPhone")
    storage.hset("product:1", "price", 9999)
    print(f"   Product: {storage.hgetall('product:1')}")
    
    # 保存
    storage.save()
    print("   ✓ Saved to ./data/app_storage.json")
    
    # 3. SQLite存储（适合生产）
    print("\n3. SQLiteStorage（SQLite数据库存储）")
    storage = SQLiteStorage("./data/app_storage.db")
    
    storage.set("session:abc123", {"user_id": 1, "expires": 3600}, ttl=3600)
    print(f"   Session: {storage.get('session:abc123')}")
    print(f"   TTL: {storage.ttl('session:abc123')} seconds")
    
    # 4. 工厂函数
    print("\n4. create_storage（工厂函数）")
    storage = create_storage("json", "./data/factory_storage.json")
    print(f"   Created: {storage}")
    
    print("\n✅ Storage examples completed!")


# ==================== Memory 组件示例 ====================

def memory_basic_examples():
    """Memory组件基本使用示例"""
    print("\n" + "=" * 60)
    print("Memory Component - Basic Examples")
    print("=" * 60)
    
    from alphora.memory import MemoryManager
    
    # 1. 创建记忆管理器
    print("\n1. 创建MemoryManager")
    memory = MemoryManager()
    print(f"   Created: {memory}")
    
    # 2. 添加对话记忆
    print("\n2. 添加对话记忆")
    memory.add_memory(
        role="user",
        content="你好，我是一名Python初学者",
        memory_id="chat_001"
    )
    memory.add_memory(
        role="assistant",
        content="你好！很高兴认识你。Python是一门很适合初学者的编程语言。",
        memory_id="chat_001"
    )
    memory.add_memory(
        role="user",
        content="我应该从哪里开始学习？",
        memory_id="chat_001"
    )
    memory.add_memory(
        role="assistant",
        content="建议从基础语法开始，然后学习数据结构和函数。推荐使用官方教程。",
        memory_id="chat_001"
    )
    print("   ✓ Added 4 memories")
    
    # 3. 构建历史（文本格式）
    print("\n3. 构建历史（文本格式）")
    history = memory.build_history(memory_id="chat_001", max_round=5)
    print(f"   History:\n{history[:200]}...")
    
    # 4. 构建历史（消息格式）
    print("\n4. 构建历史（消息格式）")
    messages = memory.build_history(memory_id="chat_001", format="messages")
    for msg in messages[:2]:
        print(f"   {msg['role']}: {msg['content'][:30]}...")
    
    # 5. 搜索记忆
    print("\n5. 搜索记忆")
    results = memory.search("Python", memory_id="chat_001", top_k=3)
    for r in results:
        print(f"   Score: {r.score:.2f} | {r.memory.get_content_text()[:40]}...")
    
    # 6. 查看统计
    print("\n6. 查看统计")
    stats = memory.stats("chat_001")
    print(f"   Count: {stats['count']}")
    print(f"   Turns: {stats['turns']}")
    print(f"   Avg Score: {stats['avg_score']:.2f}")
    
    print("\n✅ Basic examples completed!")
    return memory


def memory_advanced_examples():
    """Memory组件高级使用示例"""
    print("\n" + "=" * 60)
    print("Memory Component - Advanced Examples")
    print("=" * 60)
    
    from alphora.memory import (
        MemoryManager,
        MemoryType,
        get_decay_strategy,
        get_retrieval_strategy
    )
    
    # 1. 自定义衰减策略
    print("\n1. 自定义衰减策略")
    memory = MemoryManager(
        decay_strategy="exponential",  # 使用指数衰减
    )
    print("   Using exponential decay strategy")
    
    # 2. 使用持久化存储
    print("\n2. 持久化存储")
    memory = MemoryManager(
        storage_path="./data/chat_memory.json",
        storage_type="json",
        auto_save=True
    )
    
    memory.add_memory("user", "这条消息会被持久化", memory_id="persist_demo")
    memory.save()
    print("   ✓ Memory saved to ./data/chat_memory.json")
    
    # 3. 带重要性和标签的记忆
    print("\n3. 添加带元数据的记忆")
    memory.add_memory(
        role="user",
        content="我的API密钥是sk-xxx123（请保密）",
        memory_id="important_chat",
        importance=0.9,  # 高重要性
        tags=["api", "密钥", "机密"],
        metadata={"category": "credentials", "sensitive": True}
    )
    print("   ✓ Added memory with importance=0.9 and tags")
    
    # 4. 检索策略
    print("\n4. 不同的检索策略")
    
    # 添加一些测试数据
    for i, content in enumerate([
        "Python是一门编程语言",
        "JavaScript用于Web开发",
        "机器学习需要大量数据",
        "深度学习是机器学习的子集",
        "PyTorch是深度学习框架"
    ]):
        memory.add_memory("assistant", content, memory_id="tech_chat")
    
    # 关键词检索
    results = memory.search("机器学习", memory_id="tech_chat", strategy="keyword")
    print(f"   Keyword search: found {len(results)} results")
    
    # 模糊检索
    results = memory.search("学习", memory_id="tech_chat", strategy="fuzzy")
    print(f"   Fuzzy search: found {len(results)} results")
    
    # 5. 记忆遗忘
    print("\n5. 记忆遗忘")
    forgotten = memory.forget(
        memory_id="tech_chat",
        threshold=0.3,  # 遗忘分数低于0.3的记忆
        keep_important=True  # 但保留重要的
    )
    print(f"   Forgotten {forgotten} low-score memories")
    
    # 6. 多会话管理
    print("\n6. 多会话管理")
    memory.add_memory("user", "会话A的消息", memory_id="session_A")
    memory.add_memory("user", "会话B的消息", memory_id="session_B")
    
    global_stats = memory.stats()
    print(f"   Total memories: {global_stats['total_memories']}")
    print(f"   Memory IDs: {global_stats['memory_ids']}")
    
    print("\n✅ Advanced examples completed!")


async def memory_reflection_example():
    """Memory反思功能示例（需要LLM）"""
    print("\n" + "=" * 60)
    print("Memory Component - Reflection Example")
    print("=" * 60)
    
    # 注意：这里使用Mock LLM演示
    # 实际使用时请替换为真实的LLM
    
    class MockLLM:
        """模拟LLM用于演示"""
        async def ainvoke(self, message: str) -> str:
            # 模拟返回
            if "摘要" in message or "SUMMARY" in message.upper():
                return "用户是一名Python初学者，正在寻求学习建议。助手推荐了从基础语法开始学习的方法。"
            return '''{"summary": "关于Python学习的对话", "insights": ["用户是初学者", "需要系统学习"], "key_decisions": ["从基础开始"], "user_needs": ["学习资源", "指导"], "purpose": "学习咨询"}'''
    
    from alphora.memory import MemoryManager, MemoryReflector, create_memory
    
    # 使用Mock LLM
    llm = MockLLM()
    
    print("\n1. 使用LLM创建MemoryManager")
    memory = MemoryManager(
        llm=llm,
        auto_reflect=True,
        reflect_threshold=5  # 每5条记忆触发反思
    )
    print("   ✓ Created with auto_reflect=True")
    
    # 添加一些记忆
    print("\n2. 添加记忆")
    conversations = [
        ("user", "你好，我想学Python"),
        ("assistant", "好的，Python很适合初学者"),
        ("user", "我应该先学什么？"),
        ("assistant", "建议从变量和数据类型开始"),
        ("user", "有推荐的教程吗？"),
        ("assistant", "推荐官方文档和廖雪峰教程"),
    ]
    
    for role, content in conversations:
        memory.add_memory(role, content, memory_id="reflect_demo")
    print(f"   Added {len(conversations)} memories")
    
    # 手动触发反思
    print("\n3. 手动触发反思")
    reflection = await memory.reflect(memory_id="reflect_demo")
    if reflection:
        print(f"   Summary: {reflection.summary}")
        print(f"   Insights: {reflection.insights}")
    
    # 生成摘要
    print("\n4. 生成摘要")
    summary = await memory.summarize(memory_id="reflect_demo")
    print(f"   {summary}")
    
    # 提取关键信息
    print("\n5. 提取关键信息")
    key_info = await memory.extract_key_info(memory_id="reflect_demo")
    print(f"   Topics: {key_info.get('topics', [])}")
    print(f"   User needs: {key_info.get('user_needs', [])}")
    
    print("\n✅ Reflection example completed!")


def memory_with_real_llm_example():
    """使用真实LLM的示例代码（仅展示，不执行）"""
    print("\n" + "=" * 60)
    print("Memory with Real LLM (Code Example)")
    print("=" * 60)
    
    code = '''
# 使用真实LLM的示例

from alphora.models import OpenAILike
from alphora.memory import MemoryManager
import asyncio

# 1. 初始化LLM
llm = OpenAILike(
    api_key="sk-68ac5f5ccf3540ba834deeeaecb48987",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    model_name="qwen-plus",
    max_tokens=8000
)

# 2. 创建带LLM的MemoryManager
memory = MemoryManager(
    storage_path="./data/chat_memory.db",
    storage_type="sqlite",
    llm=llm,
    auto_reflect=True,
    reflect_threshold=20  # 每20条触发反思
)

# 3. 正常使用
memory.add_memory("user", "用户消息", memory_id="chat_001")
memory.add_memory("assistant", "助手回复", memory_id="chat_001")

# 4. 构建历史（会自动包含反思摘要）
history = memory.build_history(
    memory_id="chat_001",
    max_round=10,
    include_reflections=True
)

# 5. 手动反思
async def do_reflection():
    summary = await memory.summarize(memory_id="chat_001")
    print(f"Summary: {summary}")
    
    reflection = await memory.reflect(memory_id="chat_001")
    print(f"Insights: {reflection.insights}")

asyncio.run(do_reflection())
'''
    print(code)
    print("\n✅ Code example shown!")


def run_all_examples():
    """运行所有示例"""
    print("\n" + "=" * 60)
    print("   ALPHORA STORAGE & MEMORY EXAMPLES")
    print("=" * 60)
    
    # 创建数据目录
    import os
    os.makedirs("./data", exist_ok=True)
    
    # Storage示例
    storage_examples()
    
    # Memory基本示例
    memory_basic_examples()
    
    # Memory高级示例
    memory_advanced_examples()
    
    # Memory反思示例
    asyncio.run(memory_reflection_example())
    
    # 真实LLM代码示例
    memory_with_real_llm_example()
    
    print("\n" + "=" * 60)
    print("   ✅ ALL EXAMPLES COMPLETED!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_examples()
