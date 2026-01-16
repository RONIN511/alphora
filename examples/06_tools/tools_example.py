import asyncio
import json
import logging
from typing import Annotated
from pydantic import Field

from alphora.tools import tool, ToolRegistry, ToolExecutor

from alphora.agent import BaseAgent

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
        city: str,
        days: int
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


class ToolCallAgent(BaseAgent):
    async def main(self, query: str):
        registry = ToolRegistry()
        # 注册函数
        registry.register(get_system_time)
        registry.register(get_city_weather)

        tools_schema = registry.get_openai_tools_schema()
        executor = ToolExecutor(registry)

        prompt = "请你调用工具回答用户问题, 用户: {{query}}"
        tool_prompter = self.create_prompt(system_prompt='你是一个不按常理出牌的AI助手')

        trans_prompt = "你是一个翻译助手，可以把用户问题翻译为{{target_lang}}, 用户:{{query}}"
        trans_prompter = self.create_prompt(user_prompt=trans_prompt)
        trans_prompter.update_placeholder(target_lang='en')
        resp1 = await trans_prompter.acall(query='你好', is_stream=True)
        print(resp1)

        resp = await tool_prompter.acall(query=query, tools=tools_schema)
        print(resp)

        resp2 = await executor.execute(tool_calls=resp)
        print(resp2)
        return resp


async def main():
    from alphora.models import OpenAILike

    llm = OpenAILike()

    tca = ToolCallAgent(llm=llm)

    await tca.main(query='武汉明天天气?')


if __name__ == "__main__":
    asyncio.run(main())
