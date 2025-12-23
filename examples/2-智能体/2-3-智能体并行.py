from typing import Dict

from alphora.agent.base import BaseAgent
# from alphora.agent.models import AgentInput, AgentOutput
from alphora.models.llms.openai_like import OpenAILike
from alphora.server.stream_responser import DataStreamer
import asyncio

from alphora.server.openai_request_body import OpenAIRequest

llm_api_key: str = 'sk-68ac5f5ccf3540ba834deeeaecb48987'
llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
llm_model_name: str = "qwen-plus"


llm = OpenAILike(api_key=llm_api_key, base_url=llm_base_url, model_name='qwen-plus')


class TransAgent(BaseAgent):
    async def translate(self, query):
        en_prompt = self.create_prompt(prompt="你是一个翻译官:{{ query }}，将翻译到英文", content_type='en')
        jp_prompt = self.create_prompt(prompt="你是一个翻译官:{{ query }}，将翻译到日文", content_type='jp')

        prompt = en_prompt | jp_prompt
        res = await prompt.acall(query=query, is_stream=True, force_json=False)
        return res


class GuideAgent(BaseAgent):

    async def guide(self, query):
        trans_agent = self.derive(TransAgent)  # 派生出一个智能体
        history = self.memory.build_history()
        prompt = self.create_prompt(prompt="你是一个导游，目前正在带领一个美国旅行团，你用中文回答游客的问题。\n\n历史记录：{{history}}\n\n游客说:{{query}}",
                                    content_type='jj')
        prompt.update_placeholder(history=history)
        print(prompt.render())
        guide_resp = await prompt.acall(query=query, is_stream=True, force_json=False)
        res = await trans_agent.translate(query=guide_resp)
        self.memory.add_memory(role='游客', content='query')
        self.memory.add_memory(role='导游', content=guide_resp)
        await self.stream.astop(stop_reason='111')

    async def api_logic(self, request: OpenAIRequest):
        query = request.get_user_query()
        await self.guide(query)


# if __name__ == '__main__':
#     import uvicorn
#     app = GuideAgent(llm=llm).to_api(method='api_logic')
#     uvicorn.run(app, host="0.0.0.0", port=8000)
