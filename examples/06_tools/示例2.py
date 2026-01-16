import asyncio
import logging
import json
from typing import List, Dict, Any

# 1. 导入 Alphora 组件
from alphora.agent import BaseAgent
from alphora.models import OpenAILike
from alphora.tools import tool, ToolRegistry, ToolExecutor
from alphora.models.llms.types import ToolCall

from pydantic import Field

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(message)s')
logger = logging.getLogger("SRE_Agent")

# ==============================================================================
# 1. 定义具有"依赖关系"的工具链
# ==============================================================================

@tool
def get_alert_summary(scope: str = "all"):
    """
    获取当前集群的报警摘要。这是排查的第一步。
    """
    logger.info("正在拉取报警看板...")
    return {
        "critical_alerts": [
            {"id": "ALERT-99", "msg": "Checkout Service Latency High", "service_id": "svc-checkout-v2"}
        ],
        "warning_alerts": []
    }

@tool
def get_service_env_vars(service_id: str):
    """
    获取指定服务的环境变量配置。需要提供 service_id。
    """
    logger.info(f"正在读取 {service_id} 的环境变量配置...")
    if service_id == "svc-checkout-v2":
        return {
            "ENV": "production",
            "DB_HOST": "10.0.0.5",
            "REDIS_HOST": "redis-cache-prod.local", # 埋点：这里配置可能是错的，或者对应的Redis有问题
            "LOG_LEVEL": "DEBUG"
        }
    return {"error": "Service ID not found"}

@tool
def query_log_search(query_string: str, limit: int = 3):
    """
    搜索日志中心。建议搜索具体的报错信息或服务名。
    """
    logger.info(f"正在搜索日志: '{query_string}'")

    # 模拟：如果搜索 Redis 相关错误
    if "redis" in query_string.lower() or "svc-checkout-v2" in query_string.lower():
        return [
            "ERROR: Connection refused to redis-cache-prod.local:6379",
            "ERROR: DNS resolution failed for redis-cache-prod.local",
            "FATAL: Cache dependency missing, application crashing"
        ]
    return ["INFO: Health check passed"]

@tool
def resolve_dns(hostname: str):
    """
    诊断工具：检查内部域名解析是否正常。
    """
    logger.info(f"正在尝试解析域名: {hostname}")
    if hostname == "redis-cache-prod.local":
        return {"status": "NXDOMAIN", "ip": None, "error": "Domain does not exist"}
    return {"status": "OK", "ip": "10.0.0.5"}

@tool
def update_config_map(service_id: str, key: str, value: str):
    """
    修复工具：更新服务的配置映射。
    """
    logger.info(f"正在更新 {service_id} 配置: {key}={value}")
    return {"status": "success", "msg": "Config updated, rolling restart triggered."}


async def run_multi_turn_session(user_query: str):
    # --- 初始化 ---
    registry = ToolRegistry()
    registry.register(get_alert_summary)
    registry.register(get_service_env_vars)
    registry.register(query_log_search)
    registry.register(resolve_dns)
    registry.register(update_config_map)

    executor = ToolExecutor(registry)
    llm = OpenAILike() # 假设配置好了 API Key

    # 核心：System Prompt 必须教导模型像人类一样思考
    system_prompt = """你是一个高级故障排查助手。
你必须通过多步推理来解决问题。
不要猜测，每一步都要基于上一步工具返回的真实证据。

思考流程示例：
1. 先看报警摘要。
2. 拿到服务ID后，查它的日志或配置。
3. 发现具体错误（如DNS错误），验证该错误。
4. 执行修复。
"""

    agent = BaseAgent(llm=llm)
    prompt = agent.create_prompt(
        system_prompt=system_prompt,
        enable_memory=True    # 开启记忆至关重要
    )

    print(f"\n🔵 [User]: {user_query}")

    # --- 循环逻辑 (ReAct Loop) ---
    max_turns = 10
    current_turn = 0

    while current_turn < max_turns:
        current_turn += 1
        print(f"\n--- Turn {current_turn} ---")

        # 1. LLM 思考并决定行动
        tool_calls = await prompt.acall(
            query=user_query if current_turn == 1 else None, # 后续轮次不需要重复发 query，主要依赖 memory
            tools=registry.get_openai_tools_schema(),
            system_prompt='如果您觉得无需再调用工具，请直接返回文字输出内容'
        )

        # 2. 判断 LLM 的响应类型
        # 情况 A: LLM 决定调用工具 (ToolCall)
        if tool_calls:

            print(f"🟡 [Agent 思考]: 我需要获取更多信息，决定调用 {len(tool_calls)} 个工具。")

            # 执行所有工具
            execution_results = await executor.execute(tool_calls)

            # 打印过程
            for tc in tool_calls:
                print(f"   🔧 Call: {tc})")

            # 3. 将结果写回记忆 (Observation)
            # 注意：在 Alphora 中，我们需要将工具结果作为上下文存入，
            # 这样下一轮 LLM 才能"看到"结果。
            memory = prompt.get_memory()

            # 将工具调用的结果构建为易读的文本或结构化数据存入
            # 这里模拟 OpenAI 的 function role 逻辑
            observation_text = json.dumps(execution_results, ensure_ascii=False)
            print(f"🟢 [Tools 结果]: {observation_text[:100]}...") # 只打印前100字符

            memory.add_memory(
                role='function',  # 或者 'user'，取决于框架的具体定义，通常 'function' 或 'tool' 更准确
                content=f"Tool Outputs: {observation_text}"
            )

            # 循环继续，进入下一轮思考...

        # 情况 B: LLM 输出纯文本 (Final Answer)
        else:
            final_answer = tool_calls
            print(f"🔵 [Agent 最终回复]:\n{final_answer}")
            break

# ==============================================================================
# 3. 运行演示
# ==============================================================================

if __name__ == "__main__":
    # 场景：用户只说"系统有问题"，完全依赖 Agent 自己去探索
    query = "系统好像出问题了，报警一直在响，请帮我处理并修复它。"

    try:
        asyncio.run(run_multi_turn_session(query))
    except Exception as e:
        logger.error(f"Execution failed: {e}", exc_info=True)