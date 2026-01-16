import asyncio
import os
import json
import logging
from typing import List, Dict

# 1. 导入 Alphora 核心组件
from alphora.agent import BaseAgent
from alphora.models import OpenAILike
from alphora.tools import tool, ToolRegistry, ToolExecutor
from alphora.models.llms.types import ToolCall

# 2. 导入 Pydantic 用于参数定义
from pydantic import Field

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==============================================================================
# 1. 定义真实的运维工具 (Real-world DevOps Tools)
# ==============================================================================

@tool
def check_server_health(ip: str = Field(..., description="服务器IP地址")):
    """
    检查指定服务器的健康状态（CPU、内存、磁盘）。
    """
    logger.info(f"正在连接 {ip} 检查健康状态...")
    # 模拟真实数据：假设 192.168.1.100 负载很高
    if ip == "192.168.1.100":
        return {
            "status": "warning",
            "cpu_usage": "92%",
            "memory_usage": "85%",
            "disk_free": "12GB",
            "active_alerts": ["High CPU Load"]
        }
    return {
        "status": "healthy",
        "cpu_usage": "15%",
        "memory_usage": "40%",
        "disk_free": "200GB",
        "active_alerts": []
    }

@tool
async def fetch_error_logs(
        service_name: str,
        lines: int = 5
):
    """
    获取指定服务的最近几条错误日志。
    """
    await asyncio.sleep(1)    # 模拟 IO 耗时
    logger.info(f"正在读取 {service_name} 的日志...")

    if service_name == "payment-service":
        return [
            "ERROR 2023-10-27 10:01:05 - Connection timed out to DB-01",
            "ERROR 2023-10-27 10:01:06 - Retry attempt 1 failed",
            "CRITICAL 2023-10-27 10:01:07 - Transaction aborted"
        ]
    return ["INFO: Service is running smoothly."]


@tool
def restart_service(
        service_name: str,
        confirm_backup: bool = Field(..., description="必须确认已备份数据才能重启")
):
    """
    重启服务。注意：这是一个高风险操作，模型必须先确认备份。
    """
    if not confirm_backup:
        raise ValueError("安全拦截：未确认数据备份，无法执行重启操作！")

    logger.warning(f"正在执行重启操作: {service_name}...")
    return {"status": "success", "message": f"Service '{service_name}' restarted successfully."}


# ==============================================================================
# 2. 构建 Agent 循环 (The Agent Loop)
# ==============================================================================

async def run_agent_loop(query: str):

    # 步骤 A: 初始化环境

    # 1. 注册工具
    registry = ToolRegistry()
    registry.register(check_server_health)
    registry.register(fetch_error_logs)
    registry.register(restart_service)

    # 2. 获取 Schema 用于传给 LLM
    tools_schema = registry.get_openai_tools_schema()

    # 3. 初始化执行器
    executor = ToolExecutor(registry)

    # 4. 初始化 LLM 和 Agent
    llm = OpenAILike()
    agent = BaseAgent(llm=llm)

    # 5. 创建 Prompt (启用记忆以维护多轮对话状态)
    system_prompt = """你是一个资深的 SRE 运维专家。
你的职责是诊断系统故障并修复问题。
- 在采取危险操作（如重启）前，必须仔细分析日志。
- 只有在确认安全后才能调用执行类工具。
- 请用简洁专业的风格回答。
"""
    prompt = agent.create_prompt(
        system_prompt=system_prompt,
        enable_memory=True,       # 开启记忆，存储 LLM 的思考和工具的返回
    )

    print(f"\n🔵 [User]: {query}")

    # -------------------------------------------------
    # 步骤 B: 第一轮 - LLM 思考与决定工具
    # -------------------------------------------------
    print("🟡 [Agent]: 正在分析需求并规划工具调用...")

    for _ in range(10):
        tool_calls: ToolCall = await prompt.acall(
            query=query,
            is_stream=False,
            tools=tools_schema,
            system_prompt='如果你认为无需调用工具，请直接输出回答'
        )

        if not tool_calls:
            resp = tool_calls.content
            print(resp)
            break

        print(f"   -> 模型决定调用 {len(tool_calls)} 个工具")

        # 步骤 C: 执行工具 (Action)
        for tc in tool_calls:
            print(f"   - 调用工具: {tc}")

        tool_outputs = await executor.execute(tool_calls)

        print(f"🟢 [Tools]: 执行完成，获取到 {len(tool_outputs)} 个结果")

        # 步骤 D: 将工具结果回传给 LLM (Observation)

        print("🟡 [Agent]: 根据工具结果进行最终诊断...")

        mm = prompt.get_memory()

        mm.add_memory(role='user',
                      content=f"工具执行结果: {tool_outputs}")



# ==============================================================================
# 3. 运行入口
# ==============================================================================

if __name__ == "__main__":
    # 场景：服务器报警，Agent 需要自主诊断
    # 预期流程：
    # 1. 检查服务器健康 -> 发现 CPU 高
    # 2. 自动决定去查 'payment-service' 的日志 -> 发现 DB 链接错误
    # 3. 建议用户（或尝试）修复

    user_query = "服务器 192.168.1.100 报警了，帮我排查一下原因，如果是支付服务的问题，请告诉我具体的错误日志。"

    try:
        asyncio.run(run_agent_loop(user_query))
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"运行出错: {e}")