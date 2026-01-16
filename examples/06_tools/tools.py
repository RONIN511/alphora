import asyncio
import json
import logging
from typing import Annotated
from pydantic import Field

from alphora.tools import tool, ToolRegistry, ToolExecutor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@tool
def get_system_time(format: str = "%Y-%m-%d %H:%M:%S"):
    """
    获取当前系统的本地时间。
    """
    from datetime import datetime
    return datetime.now().strftime(format)


@tool(name="weather_service")
async def get_city_weather(
        city: str = Field(..., description="城市名称，例如: Beijing, Hangzhou"),
        days: int = Field(1, ge=1, le=7, description="预测天数 (1-7天)")
):
    """
    查询指定城市的未来天气预报。
    """
    # 模拟网络 IO 延迟
    await asyncio.sleep(0.5)

    # 模拟业务逻辑：特定城市报错
    if city.lower() == "unknown":
        raise ValueError(f"City '{city}' not found in weather database.")

    return {
        "city": city,
        "forecast": [
            {"day": i+1, "status": "Sunny", "temp": 25 + i}
            for i in range(days)
        ]
    }


class DatabaseAgent:
    def __init__(self, db_url: str):
        self.db_url = db_url

    def query_user_info(self, user_id: int):
        """根据 User ID 查询用户详细档案"""
        # 这里演示了如何在工具内部访问 self.db_url
        return f"User(id={user_id}, name='Alice') from DB({self.db_url})"


# 初始化服务实例
db_service = DatabaseAgent("postgres://localhost:5432/users")


# 注册与 Schema 生成 (Registration)
async def main():
    print(">>> 1. 初始化注册表...")
    registry = ToolRegistry()

    # 注册函数
    registry.register(get_system_time)
    registry.register(get_city_weather)

    # 注册实例方法 (支持重命名)
    registry.register(db_service.query_user_info, name_override="lookup_user")

    # 打印生成的 JSON Schema (给大模型看的内容)
    print("\n>>> 2. 生成 OpenAI Tools Schema:")
    tools_schema = registry.get_openai_tools_schema()

    print(json.dumps(tools_schema, indent=2, ensure_ascii=False))

    # ==========================================
    # 3. 模拟大模型调用 (Execution Simulation)
    # ==========================================
    executor = ToolExecutor(registry)

    print("\n>>> 3. 开始模拟 Agent 执行流程...")

    # --- Case 1: 正常并行调用 (Parallel Execution) ---
    print("\n[Case 1] 模拟 LLM 并发调用两个工具:")
    mock_llm_response_1 = [
        {
            "id": "call_abc123",
            "type": "function",
            "function": {
                "name": "weather_service",
                "arguments": json.dumps({"city": "Hangzhou", "days": 3})
            }
        },
        {
            "id": "call_def456",
            "type": "function",
            "function": {
                "name": "get_system_time",
                "arguments": "{}" # 使用默认参数
            }
        }
    ]

    results = await executor.execute(mock_llm_response_1)
    print("执行结果:")
    print(json.dumps(results, indent=2, ensure_ascii=False))


    # --- Case 2: 错误恢复 (Error Recovery - Pydantic Validation) ---
    print("\n[Case 2] 模拟参数校验失败 (LLM 传参错误):")
    # 场景：days 参数超过了 max=7 的限制
    mock_llm_response_2 = [
        {
            "id": "call_err001",
            "type": "function",
            "function": {
                "name": "weather_service",
                "arguments": json.dumps({"city": "Beijing", "days": 100})
            }
        }
    ]

    results_validation = await executor.execute(mock_llm_response_2)
    print("执行结果 (注意 content 中的错误提示):")
    print(json.dumps(results_validation, indent=2, ensure_ascii=False))


    # --- Case 3: 运行时异常 (Runtime Error) ---
    print("\n[Case 3] 模拟业务逻辑报错:")
    mock_llm_response_3 = [
        {
            "id": "call_err002",
            "type": "function",
            "function": {
                "name": "weather_service",
                "arguments": json.dumps({"city": "Unknown", "days": 1})
            }
        }
    ]

    results_runtime = await executor.execute(mock_llm_response_3)
    print("执行结果 (业务异常捕获):")
    print(json.dumps(results_runtime, indent=2, ensure_ascii=False))

    # --- Case 4: 调用类方法 (Instance Method) ---
    print("\n[Case 4] 调用绑定实例的方法:")
    mock_llm_response_4 = [
        {
            "id": "call_cls001",
            "type": "function",
            "function": {
                "name": "lookup_user", # 使用了 name_override
                "arguments": json.dumps({"user_id": 888})
            }
        }
    ]
    results_cls = await executor.execute(mock_llm_response_4)
    print("执行结果:")
    print(json.dumps(results_cls, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
