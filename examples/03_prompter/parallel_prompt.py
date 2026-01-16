import asyncio
import os
import time
import json
from collections import Counter
from alphora.agent import BaseAgent
from alphora.models import OpenAILike
from alphora.prompter.parallel import ParallelPrompt


def get_llm():
    # 请确保环境变量已设置，或在此处直接填入 key
    return OpenAILike()


async def example_1_parallel_operator():
    print("\n--- 示例 1: 使用 | 操作符创建并行 Prompt ---")
    llm = get_llm()
    agent = BaseAgent(llm=llm)

    # 定义三个不同任务的 Prompt
    p1 = agent.create_prompt(system_prompt="你是一个中英翻译专家，只输出结果。")
    p2 = agent.create_prompt(system_prompt="你是一个摘要专家，用一句话概括。")
    p3 = agent.create_prompt(system_prompt="你是一个情感分析专家，只输出：积极/消极/中性。")

    # 使用 | 组合
    parallel_prompt = p1 | p2 | p3

    text = "人工智能正在改变我们的生活方式，带来前所未有的便利。"
    print(f"输入文本: {text}\n正在并行调用...")

    start = time.time()
    results = await parallel_prompt.acall(query=text, is_stream=False)

    print(f"耗时: {time.time() - start:.2f}s")
    print(f"1. 翻译: {results[0]}")
    print(f"2. 摘要: {results[1]}")
    print(f"3. 情感: {results[2]}")


async def example_2_serial_vs_parallel():
    print("\n--- 示例 2: 串行 vs 并行效率对比 ---")
    llm = get_llm()
    agent = BaseAgent(llm=llm)

    prompts = [agent.create_prompt(system_prompt="简短回答。") for _ in range(3)]
    query = "请问 1+1 等于几？"

    # 串行
    print("开始串行调用...")
    s_start = time.time()
    for p in prompts:
        await p.acall(query=query, is_stream=False)
    s_time = time.time() - s_start
    print(f"串行总耗时: {s_time:.2f}s")

    # 并行
    print("开始并行调用...")
    p_prompt = prompts[0] | prompts[1] | prompts[2]
    p_start = time.time()
    await p_prompt.acall(query=query, is_stream=False)
    p_time = time.time() - p_start
    print(f"并行总耗时: {p_time:.2f}s")
    print(f"效率提升约: {s_time / p_time:.1f}x")


async def example_3_multi_perspective():
    print("\n--- 示例 3: 多角度分析 (技术/商业/风险/体验) ---")
    llm = get_llm()
    agent = BaseAgent(llm=llm)

    roles = ["技术专家", "商业分析师", "风险评估师", "用户体验师"]
    prompts = [agent.create_prompt(system_prompt=f"你是{role}，请简要分析下述项目。") for role in roles]

    parallel_prompt = prompts[0] | prompts[1] | prompts[2] | prompts[3]
    question = "开发一款 AI 驱动的个人健康助手 App"

    results = await parallel_prompt.acall(query=question, is_stream=False)
    for role, res in zip(roles, results):
        print(f"\n【{role}】: {res}")


async def example_4_voting():
    print("\n--- 示例 4: 投票机制 (5个评委) ---")
    llm = get_llm()
    agent = BaseAgent(llm=llm)

    p = agent.create_prompt(system_prompt="判断对错，只回答'正确'或'错误'")
    # 模拟5个独立请求
    parallel_prompt = p | p | p | p | p

    statement = "地球是太阳系中最大的行星"
    print(f"陈述: {statement}")
    results = await parallel_prompt.acall(query=statement, is_stream=False)

    votes = [r.strip().replace("。", "") for r in results]
    count = Counter(votes)
    print(f"详细投票: {votes}")
    print(f"最终结论: {count.most_common(1)[0][0]}")


async def example_5_with_placeholders():
    print("\n--- 示例 5: 带占位符的并行 Prompt ---")
    llm = get_llm()
    agent = BaseAgent(llm=llm)

    p1 = agent.create_prompt(prompt="将文本翻译成{{lang}}: {{query}}")
    p2 = agent.create_prompt(prompt="以{{style}}风格改写: {{query}}")

    p1.update_placeholder(lang="法语")
    p2.update_placeholder(style="武侠")

    results = await (p1 | p2).acall(query="How are you?", is_stream=False)
    print(f"法语翻译: {results[0]}")
    print(f"武侠改写: {results[1]}")


async def example_6_direct_class():
    print("\n--- 示例 6: 直接使用 ParallelPrompt 类 ---")
    llm = get_llm()
    agent = BaseAgent(llm=llm)

    # 列表形式构建
    prompt_list = [agent.create_prompt(system_prompt=f"你是助手{i}") for i in range(3)]
    pp = ParallelPrompt(prompt_list)

    results = await pp.acall(query="嘿！", is_stream=False)
    print(f"收到 {len(results)} 个回复")


def example_7_sync_call():
    print("\n--- 示例 7: 同步并行调用 (Parallel .call) ---")
    llm = get_llm()
    agent = BaseAgent(llm=llm)

    pp = agent.create_prompt(system_prompt="助手A") | agent.create_prompt(system_prompt="助手B")
    # 注意这里不是 await，是直接 .call
    results = pp.call(query="你好", is_stream=False)
    print(f"同步获取结果: {results}")


# ============================================================
# 交互菜单
# ============================================================

async def main_menu():
    menu = {
        "1": ("| 操作符基础组合", example_1_parallel_operator),
        "2": ("串行 vs 并行效率对比", example_2_serial_vs_parallel),
        "3": ("多角度业务分析", example_3_multi_perspective),
        "4": ("LLM 投票机制", example_4_voting),
        "5": ("并行占位符更新", example_5_with_placeholders),
        "6": ("使用 ParallelPrompt 类", example_6_direct_class),
        "7": ("同步并行调用 (Sync)", example_7_sync_call),
    }

    while True:
        print("\n" + "■" * 45)
        print("    Alphora ParallelPrompt 并行模式调试")
        print("■" * 45)
        for k, v in menu.items():
            print(f" [{k}] {v[0]}")
        print(" [q] 退出")
        print("-" * 45)

        choice = input("请选择案例序号: ").strip().lower()

        if choice == 'q':
            break

        if choice in menu:
            func = menu[choice][1]
            try:
                if asyncio.iscoroutinefunction(func):
                    await func()
                else:
                    func()
            except Exception as e:
                print(f"\n[错误]: {e}")
            input("\n回车继续...")
        else:
            print("输入有误，请重试。")


if __name__ == "__main__":
    try:
        asyncio.run(main_menu())
    except KeyboardInterrupt:
        pass
