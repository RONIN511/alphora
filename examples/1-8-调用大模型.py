from alphora.models import OpenAILike


llm_api_key: str = "sk-68ac5f5ccf3540ba834deeeaecb48987"  # 替换为您的API密钥
llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"  # 通义千问兼容OpenAI的API地址
llm_model_name: str = "qwen-plus"

# 初始化LLM模型
llm = OpenAILike(
    api_key=llm_api_key,
    base_url=llm_base_url,
    model_name=llm_model_name,
    max_tokens=8000
)


async def main():
    resp = await llm.ainvoke(message='你好')
    print(resp)
    return


if __name__ == '__main__':
    import asyncio
    _ = asyncio.run(main())
