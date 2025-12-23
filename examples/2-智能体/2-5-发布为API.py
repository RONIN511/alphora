from alphora.agent.base import BaseAgent
from alphora.models.llms.openai_like import OpenAILike

from alphora.server.openai_request_body import OpenAIRequest

llm_api_key: str = 'sk-68ac5f5ccf3540ba834deeeaecb48987'
llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
llm_model_name: str = "qwen-plus"


llm = OpenAILike(api_key=llm_api_key, base_url=llm_base_url, model_name='qwen-plus', max_tokens=8000)


class TeacherAgent(BaseAgent):
    async def teacher(self, query):

        history = self.memory.build_history()

        prompt = self.create_prompt(prompt="你是一个AI助手，目前正在回复用户的问题，请你准确的回复用户的问题，\n\n历史对话: \n{{history}} \n\n用户说:{{query}}")

        prompt.update_placeholder(history=history)

        print(prompt.render())
        teacher_resp = await prompt.acall(query=query, is_stream=True, force_json=False)

        self.memory.add_memory(role='用户', content=query)
        self.memory.add_memory(role='AI', content=teacher_resp)

        await self.stream.astop(stop_reason=f'{query}')

    async def api_logic(self, request: OpenAIRequest):
        query = request.get_user_query()
        await self.teacher(query)


if __name__ == '__main__':
    import uvicorn
    from alphora.server.quick_api import publish_agent_api, APIPublisherConfig

    agent = TeacherAgent(llm=llm)

    # 发布 API（传入 Agent 类 + 初始化参数）的配置信息
    config = APIPublisherConfig(
        memory_ttl=7200,  # 2小时
        max_memory_items=2000,
        auto_clean_interval=300,  # 5分钟
        api_title="{agent_name} API Service",
        api_description="Auto-generated API for {agent_name} (method: {method_name})"
    )

    # 发布API
    app = publish_agent_api(
        agent=agent,
        method="api_logic",
        config=config
    )

    uvicorn.run(app, host="0.0.0.0", port=8001)
