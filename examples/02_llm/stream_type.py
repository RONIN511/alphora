import asyncio
from alphora.models import OpenAILike
from alphora.models.message import Message

headers = {
    "Content-Type": "application/json;charset=UTF-8",
    "X-Server-Param": "eyJhcHBpZCI6ICJkc2p5eWJhaSIsICJjc2lkIjogImRzanl5YmFpcXdlbjJfNzJiX2luc3RydWN0MDAwMDAwNjVlOWJlZDlmMGNhNDEzODg5ODJjNWZmODQzMTg1NmEifQ==",
    "X-CurTime": "1769390828",
    "X-CheckSum": "3d1033957e718a05e69e92014f63a4dd"
}


def create_llm():
    """创建 LLM 实例"""
    return OpenAILike(
        api_key="chatbi",
        model_name="moa",
        base_url="http://10.217.247.48:9050/bbdata_qa",
        header=headers,
    )


async def example_streaming():
    """流式输出示例"""
    print("\n" + "=" * 60)
    print("示例 5: 流式输出")
    print("=" * 60)

    llm = create_llm()

    print("生成中: ", end="", flush=True)

    # 获取流式生成器
    generator = await llm.aget_streaming_response_dynamic(
        message="OPPO",
        content_type="text"
    )

    full_response = ""
    async for chunk in generator:
        print(chunk.content, end="", flush=True)
        # print(chunk.content_type)
        full_response += chunk.content

    print(f"\n\n完整回答长度: {len(full_response)} 字符")
    print(f"结束原因: {generator.finish_reason}")

    return full_response


if __name__ == "__main__":
    asyncio.run(example_streaming())