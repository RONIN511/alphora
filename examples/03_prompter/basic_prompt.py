import asyncio
import json
from alphora.agent import BaseAgent
from alphora.models import OpenAILike
from alphora.prompter import BasePrompt


# ============================================================
# 示例定义 (保持逻辑不变，封装进函数)
# ============================================================


async def example_system_prompt_mode():
    print("\n--- 示例 1: 使用 system_prompt 模式（推荐） ---")
    llm = OpenAILike()
    agent = BaseAgent(llm=llm)
    prompt = agent.create_prompt(system_prompt="你是一个专业的Python编程助手，回答要简洁准确。")
    response = await prompt.acall(query="什么是装饰器？", is_stream=False)
    print(f"回答: {response}")


async def example_prompt_mode():
    print("\n--- 示例 2: 使用 prompt 参数（传统模式） ---")
    llm = OpenAILike()
    agent = BaseAgent(llm=llm)
    prompt = agent.create_prompt(prompt="""请将以下文本翻译成{{target_language}}：\n{{query}}\n只输出翻译结果。""")
    prompt.update_placeholder(target_language="英文")
    response = await prompt.acall(query="人工智能正在改变世界", is_stream=False)
    print(f"翻译: {response}")


async def example_placeholder_system_prompt():
    print("\n--- 示例 3: 带占位符的 system_prompt ---")
    llm = OpenAILike()
    agent = BaseAgent(llm=llm)
    prompt = agent.create_prompt(system_prompt="你是一个{{role}}，风格是{{style}}。")
    prompt.update_placeholder(role="资深架构师", style="专业严谨")
    response = await prompt.acall(query="如何设计一个高可用的微服务架构？", is_stream=False)
    print(f"回答: {response[:150]}...")


async def example_streaming():
    print("\n--- 示例 4: 流式输出 ---")
    llm = OpenAILike()
    agent = BaseAgent(llm=llm)
    prompt = agent.create_prompt(system_prompt="你是一个故事讲述者")
    print("回答: ", end="", flush=True)
    response = await prompt.acall(query="请讲一个简短的故事", is_stream=True)
    print(f"\n[完成] 长度: {len(response)} 字符")


async def example_return_generator():
    print("\n--- 示例 5: 返回生成器 ---")
    llm = OpenAILike()
    agent = BaseAgent(llm=llm)
    prompt = agent.create_prompt(system_prompt="你是一个编程助手")
    generator = await prompt.acall(query="用Python写一个Hello World", is_stream=True, return_generator=True)
    async for chunk in generator:
        print(f"[{chunk.content_type}] {chunk.content}", end="")
    print("\n[生成完毕]")


async def example_json_output():
    print("\n--- 示例 6: JSON 输出 ---")
    llm = OpenAILike()
    agent = BaseAgent(llm=llm)
    prompt = agent.create_prompt(system_prompt="你是一个数据助手，请用JSON格式回答。")
    response = await prompt.acall(query="列出3种编程语言及其特点", is_stream=False, force_json=True)
    print(f"原始响应: {response}")
    try:
        data = json.loads(response)
        print(f"解析成功，键名: {list(data.keys())}")
    except:
        print("解析失败")


async def example_long_response():
    print("\n--- 示例 7: 长响应模式 (自动续写) ---")
    llm = OpenAILike()
    agent = BaseAgent(llm=llm)
    prompt = agent.create_prompt(system_prompt="你是一个技术文档作者")
    response = await prompt.acall(query="详细介绍Python的10个高级特性，每个都要代码", is_stream=True, long_response=True)
    print(f"\n总长度: {len(response)}，续写次数: {response.continuation_count}")


async def example_thinking_mode():
    print("\n--- 示例 8: 启用思考模式 ---")
    llm = OpenAILike()
    agent = BaseAgent(llm=llm)
    prompt = agent.create_prompt(system_prompt="你是一个数学老师")
    response = await prompt.acall(query="计算 (3 + 4) * 5 - 2", is_stream=True, enable_thinking=True)
    if response.reasoning:
        print(f"\n\n思考过程: {response.reasoning[:100]}...")
    print(f"最终答案: {response}")


async def example_prompter_output():
    print("\n--- 示例 9: PrompterOutput 对象属性 ---")
    llm = OpenAILike()
    agent = BaseAgent(llm=llm)
    prompt = agent.create_prompt(system_prompt="你是一个助手")
    response = await prompt.acall(query="你好", is_stream=False)
    print(f"finish_reason: {response.finish_reason}")
    print(f"类型: {type(response)}")


def example_render_prompt():
    print("\n--- 示例 10: 渲染和查看提示词 ---")
    agent = BaseAgent(llm=OpenAILike())
    prompt = agent.create_prompt(prompt="角色:{{role}}\n任务:{{task}}\n内容:{{query}}")
    prompt.update_placeholder(role="分析师", task="分析数据")
    print(f"渲染结果:\n{prompt.render()}")


# ============================================================
# 交互菜单逻辑
# ============================================================

async def main():
    # 建立序号与函数的映射
    menu = {
        "1": ("System Prompt 模式", example_system_prompt_mode),
        "2": ("传统 Prompt 模式", example_prompt_mode),
        "3": ("带占位符的 System Prompt", example_placeholder_system_prompt),
        "4": ("流式输出", example_streaming),
        "5": ("返回生成器", example_return_generator),
        "6": ("JSON 强制输出", example_json_output),
        "7": ("长响应模式 (慢)", example_long_response),
        "8": ("思考模式 (Reasoning)", example_thinking_mode),
        "9": ("PrompterOutput 属性查看", example_prompter_output),
        "10": ("本地渲染测试 (同步)", example_render_prompt),
    }

    while True:
        print("\n" + "=" * 40)
        print("      Alphora Prompter 示例菜单")
        print("=" * 40)
        for key, value in menu.items():
            print(f"[{key}] {value[0]}")
        print("[q] 退出程序")
        print("-" * 40)

        choice = input("请输入数字选择要运行的示例: ").strip().lower()

        if choice == 'q':
            print("退出程序。")
            break

        if choice in menu:
            func = menu[choice][1]
            try:
                # 判断是异步函数还是普通函数
                if asyncio.iscoroutinefunction(func):
                    await func()
                else:
                    func()
            except Exception as e:
                print(f"\n运行出错: {e}")

            input("\n回车以继续...")
        else:
            print("\n无效输入，请重新选择。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
