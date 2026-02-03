"""
Internet Search Agent - 互联网搜索智能体

使用博查 Web Search API 提供联网搜索能力。
文档：https://open.bochaai.com/

使用示例:
    from alphora_community.agents.internet_search import InternetSearchAgent
    
    agent = InternetSearchAgent(api_key="your-api-key")
    result = await agent.search_internet("最新AI新闻")
"""

import os
from typing import Optional, Literal

from alphora.agent import BaseAgent


class InternetSearchAgent(BaseAgent):
    """
    互联网搜索智能体
    
    使用博查 Web Search API 搜索互联网信息。
    
    Attributes:
        api_key: 博查 API Key
        api_endpoint: API 端点地址
    """

    API_ENDPOINT = "https://api.bochaai.com/v1/web-search"

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        """
        初始化搜索智能体

        Args:
            api_key: 博查 API Key，不传则从环境变量 BOCHA_API_KEY 获取
            **kwargs: 传递给 BaseAgent 的参数
        """
        super().__init__(**kwargs)
        self._api_key = api_key or os.getenv("BOCHA_API_KEY")

    def set_api_key(self, api_key: str):
        """设置 API Key"""
        self._api_key = api_key

    async def search_internet(
        self,
        query: str,
        count: int = 8,
        freshness: Literal["noLimit", "oneDay", "oneWeek", "oneMonth", "oneYear"] = "noLimit"
    ) -> str:
        """
        执行互联网实时搜索，获取最新资讯、事实验证或特定领域的知识补充。

        【核心原则：聚焦与拆解】
        1. Query 必须具体且聚焦，避免宽泛的通用词汇
        2. 复杂需求应拆解为多次搜索

        【使用场景】
        - 查询实时信息：新闻、股价、天气、赛事比分等
        - 查找最新资讯：政策法规、产品发布、行业动态
        - 验证事实：核实某个说法或数据是否准确
        - 补充知识：获取训练数据之外的新知识

        Args:
            query: 搜索关键词或问题，支持自然语言
            count: 返回结果数量，默认 8 条，最多 20 条
            freshness: 时间范围过滤
                - "noLimit": 不限时间（默认）
                - "oneDay": 最近一天
                - "oneWeek": 最近一周
                - "oneMonth": 最近一个月
                - "oneYear": 最近一年

        Returns:
            格式化的搜索结果，包含标题、来源、摘要、链接等
        """
        if not self._api_key:
            return "❌ 未配置博查 API Key，请设置环境变量 BOCHA_API_KEY 或调用 set_api_key()"

        try:
            import httpx
        except ImportError:
            return "❌ 需要安装 httpx: pip install httpx"

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "query": query,
            "count": min(count, 20),
            "freshness": freshness,
            "summary": True,
        }

        if self.stream:
            await self.stream.astream_message(content=f"🔍 正在搜索：{query}\n\n", interval=0.01)

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    self.API_ENDPOINT,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException:
            return "❌ 搜索超时，请稍后重试"
        except httpx.HTTPStatusError as e:
            return f"❌ 搜索请求失败：HTTP {e.response.status_code}"
        except Exception as e:
            return f"❌ 搜索出错：{str(e)}"

        # 流式输出简洁结果给用户
        if self.stream:
            await self._stream_to_user(data)

        # 返回给 LLM 的详细结果
        return self._format_results_for_llm(query, data)

    async def _stream_to_user(self, data: dict):
        """流式输出给用户看的简洁内容"""
        response_data = data.get("data", {})
        web_pages = response_data.get("webPages", {}).get("value", [])

        if not web_pages:
            await self.stream.astream_message(content="未找到相关结果\n", interval=0.01)
            return

        await self.stream.astream_message(content="**搜索结果**\n\n", interval=0.01)

        for i, page in enumerate(web_pages[:6], 1):
            title = page.get("name", "无标题")
            url = page.get("url", "")
            site_name = page.get("siteName", "")
            date = page.get("datePublished", "")

            source_info = site_name
            if date:
                source_info += f" · {date[:10]}"

            await self.stream.astream_message(
                content=f"**{i}. [{title}]({url})**\n",
                interval=0.01
            )
            if source_info:
                await self.stream.astream_message(
                    content=f"   {source_info}\n\n",
                    interval=0.01
                )

    def _format_results_for_llm(self, query: str, data: dict) -> str:
        """格式化给 LLM 使用的详细搜索结果"""
        lines = [f"搜索词：{query}", ""]

        response_data = data.get("data", {})
        web_pages = response_data.get("webPages", {}).get("value", [])

        if not web_pages:
            return "未找到相关结果"

        lines.append(f"共 {len(web_pages)} 条结果：\n")

        for i, page in enumerate(web_pages, 1):
            title = page.get("name", "无标题")
            url = page.get("url", "")
            site_name = page.get("siteName", "未知来源")
            snippet = page.get("snippet", "")
            summary = page.get("summary", "")
            date = page.get("datePublished", "")

            lines.append(f"【{i}】{title}")
            lines.append(f"来源：{site_name}" + (f" | {date[:10]}" if date else ""))

            content = summary or snippet
            if content:
                if len(content) > 500:
                    content = content[:500] + "..."
                lines.append(f"内容：{content}")

            lines.append(f"链接：{url}")
            lines.append("")

        return "\n".join(lines)
