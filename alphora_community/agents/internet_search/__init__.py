"""
Internet Search Agent - 互联网搜索智能体

使用博查 Web Search API 提供联网搜索能力。

快速开始:
    from alphora_community.agents.internet_search import InternetSearchAgent
    
    agent = InternetSearchAgent(api_key="your-bocha-api-key")
    
    # 搜索
    result = await agent.search_internet("最新AI新闻")
    
    # 限定时间范围
    result = await agent.search_internet(
        "GPT-5 发布",
        freshness="oneWeek"  # oneDay/oneWeek/oneMonth/oneYear/noLimit
    )

API Key 获取:
    访问 https://open.bochaai.com/ 注册获取 API Key
    或设置环境变量 BOCHA_API_KEY
"""

__version__ = "1.0.0"

from .agent import InternetSearchAgent

__all__ = ['InternetSearchAgent']
