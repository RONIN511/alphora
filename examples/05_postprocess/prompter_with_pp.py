import asyncio
import json
import re
from typing import Iterator, AsyncIterator

from alphora.agent import BaseAgent
from alphora.models import OpenAILike
from alphora.models.llms.stream_helper import BaseGenerator, GeneratorOutput

# 后处理器组件
from alphora.postprocess import FilterPP, ReplacePP, JsonKeyExtractorPP
from alphora.postprocess.pattern_match import PatternMatcherPP
from alphora.postprocess.base_pp import BasePostProcessor
from alphora.postprocess.dynamic_type import DynamicTypePP


def get_agent():
    """初始化 Agent"""
    llm = OpenAILike()
    return BaseAgent(llm=llm)


# ============================================================
# 场景 1: 敏感词实时清洗与竞品屏蔽 (ReplacePP)
# ============================================================
async def example_sensitive_filter():
    print("\n--- 场景 1: 敏感词实时清洗与竞品屏蔽 ---")
    print("业务背景: 客服机器人不能在回复中提到竞争对手的名字，且需要将特定术语标准化。\n")

    agent = get_agent()

    # 定义更丰富的 System Prompt
    system_prompt = """你是一个专业的电商客服助手。
你的任务是安抚客户情绪，并对比产品优势。
请在回复中自然地提到“拼多多”和“淘宝”作为价格对比（模拟竞品）。
"""

    # 创建 Prompt
    prompt = agent.create_prompt(system_prompt=system_prompt)

    # 定义替换规则：将竞品名称替换为通用术语
    replacer = ReplacePP(replace_map={
        "拼多多": "【已替换】友商P【已替换】",
        "淘宝": "【已替换】友商T【已替换】",
        "京东": "【已替换】我们平台【已替换】",
        "死": "【已替换】不好的体验【已替换】"  # 简单的敏感字替换
    })

    print(f"用户提问: 你们的价格比拼多多贵太多了！")
    print("流式输出 (已清洗): ", end="", flush=True)

    await prompt.acall(
        query="请解释一下为什么你们比拼多多和淘宝贵？给我一个合理的理由，不然我死给你看。",
        is_stream=True,
        postprocessor=replacer
    )
    print("\n\n[演示结束] 注意观察输出中并没有出现具体的竞品原名。")


# ============================================================
# 场景 2: 纯净代码提取 (PatternMatcherPP)
# ============================================================
async def example_code_extraction():
    print("\n--- 场景 2: 纯净代码提取模式 ---")
    print("业务背景: 用户正在使用一个代码生成插件，只想将代码直接插入编辑器，不需要大模型的废话（如'好的，这是代码...'）。\n")

    agent = get_agent()

    # 强制让模型输出 Markdown 代码块
    prompt = agent.create_prompt(system_prompt="""你是一个资深 Python 架构师。
请直接给出代码解决方案，不要解释。必须使用 ```python 包裹代码。
""")

    # 配置模式匹配器：只提取 ```python 和 ``` 之间的内容
    code_cleaner = PatternMatcherPP(
        bos="```python",  # 开始标记
        eos="```",  # 结束标记
        matched_type="code",  # 将匹配内容标记为 code 类型
        include_bos=False,  # 输出不包含 ```python
        include_eos=False,  # 输出不包含 ```
        output_mode="only_matched"  # 【关键】只输出匹配到的内容，忽略其他废话
    )

    query = "写一个使用 FastAPI 和 Pydantic 的用户注册接口示例，包含字段校验。"
    print(f"任务: {query}")
    print("流式输出 (仅代码内容): \n")
    print("-" * 30)

    await prompt.acall(
        query=query,
        is_stream=True,
        postprocessor=code_cleaner
    )
    print("\n" + "-" * 30)
    print("[演示结束] 如果模型在代码块前后说了'好的'或'注意'，这些内容都会被过滤掉。")


# ============================================================
# 场景 3: 隐藏思维链/思考过程 (PatternMatcherPP - Exclude)
# ============================================================
async def example_hide_thought():
    print("\n--- 场景 3: 隐藏思维链 (DeepSeek-R1 风格处理) ---")
    print("业务背景: 很多推理模型会输出 <think>...</think>。普通用户不需要看思考过程，只需要最终答案。\n")

    agent = get_agent()

    # 模拟一个会输出思考过程的模型 Prompt
    system_prompt = """你是一个数学天才。
在回答问题前，先在 <think> 和 </think> 标签内写下详细的推理步骤，然后再给出最终回复。
"""
    prompt = agent.create_prompt(system_prompt=system_prompt)

    # 配置：排除掉 <think>...</think> 之间的内容
    thought_hider = PatternMatcherPP(
        bos="<think>",
        eos="</think>",
        matched_type="reasoning",
        output_mode="exclude_matched"  # 【关键】排除匹配到的内容，只输出剩下的
    )

    print("问题: 鸡兔同笼，头35，脚94，各多少只？")
    print("流式输出 (已隐藏思考过程): ", end="", flush=True)

    await prompt.acall(
        query="请计算并告诉我结果。",
        is_stream=True,
        postprocessor=thought_hider
    )
    print("\n\n[演示结束] 实际上模型输出了大量思考文本，但被实时拦截了。")


# ============================================================
# 场景 4: JSON 字段精准提取 (JsonKeyExtractorPP)
# ============================================================
async def example_json_field_stream():
    print("\n--- 场景 4: JSON 字段定向流式提取 ---")
    print(
        "业务背景: 后端让 LLM 分析长文本并返回 JSON，前端 UI 需要实时打字机效果显示 'summary' 字段，而不展示整个 JSON 结构。\n")

    agent = get_agent()
    prompt = agent.create_prompt(system_prompt="""你是一个新闻分析师。
请分析用户输入的新闻，并返回严格的 JSON 格式，包含以下字段：
- "sentiment": 情感倾向 (string)
- "tags": 标签列表 (array)
- "summary": 简短的中文摘要 (string)
""")

    # 提取器：只流式输出 summary 字段的值
    extractor = JsonKeyExtractorPP(
        target_key="summary",
        output_mode="both"
    )

    news_text = """
    今日，SpaceX 的星舰进行了第五次试飞。助推器成功在发射塔被机械臂“筷子”夹住回收。
    马斯克表示这是人类迈向多行星物种的关键一步。现场欢呼声雷动，股价随后上涨了5%。
    """

    print("流式输出 (仅摘要内容): ", end="", flush=True)

    # force_json=True 会在 Prompt 中追加 JSON 约束
    full_resp = await prompt.acall(
        query=f"分析这条新闻：{news_text}",
        is_stream=True,
        force_json=True,
        postprocessor=extractor
    )

    print(f'\n\n[完整输出]:{full_resp}')
    print("\n\n[演示结束] 模型生成的是完整 JSON，但我们只看到了 summary 的内容。")


# ============================================================
# 场景 5: 组合拳 - 链式处理 (Chain)
# ============================================================
async def example_chain_processing():
    print("\n--- 场景 5: 处理器链式组合 (Filter -> Replace) ---")
    print("业务背景: 先过滤掉 Markdown 的加粗符号(**)，然后将英文标点转为 --- 连接。\n")

    agent = get_agent()
    prompt = agent.create_prompt(system_prompt="你是一个排版助手，喜欢用**加粗**强调重点。")

    # 1. 过滤器：去掉加粗符号 '*'
    filter_pp = FilterPP(filter_chars="*")

    # 2. 替换器：英文逗号转中文
    replace_pp = ReplacePP(replace_map={",": "---", ".": "---"})

    # 组合列表，按顺序执行
    chain = [filter_pp, replace_pp]

    print("原始意图: 输出带加粗和英文标点的文本")
    print("流式输出 (清洗后): ", end="", flush=True)

    await prompt.acall(
        query="请介绍一下 Python 的三个优点，用英文逗号分隔，关键词要加粗。",
        is_stream=True,
        postprocessor=chain
    )
    print("\n\n[演示结束] 加粗符号被移除，标点被规范化。")


# ============================================================
# 场景 6: 自定义处理器 - 隐私正则掩码
# ============================================================
class PrivacyMaskPP(BasePostProcessor):
    """
    自定义处理器：使用正则掩盖手机号
    注意：这只是一个简单的流式处理示例。
    在真实流式场景中，跨 chunk 的正则匹配需要更复杂的 buffer 机制，
    这里演示简单的单 chunk 处理或假设数字在同一个 chunk 中。
    """

    def process(self, generator: BaseGenerator) -> BaseGenerator:
        class MaskGenerator(BaseGenerator):
            def __init__(self, original):
                super().__init__(original.content_type)
                self.original = original

            async def agenerate(self):
                buffer = ""
                async for chunk in self.original:
                    content = chunk.content
                    # 简单的逻辑：替换所有连续 11 位数字为 [PHONE]
                    # 实际生产级流式正则需要滑动窗口
                    content = re.sub(r'\d{11}', '[隐私手机号]', content)
                    chunk.content = content
                    yield chunk

            def generate(self):
                # 同步接口实现（略）
                yield from self.original

        return MaskGenerator(generator)


async def example_custom_privacy():
    print("\n--- 场景 6: 自定义处理器 (正则掩码) ---")
    print("业务背景: 无论模型输出什么，如果检测到类似手机号的数字串，强制掩盖。\n")

    agent = get_agent()
    prompt = agent.create_prompt(system_prompt="你是一个在整理通讯录的助手。")

    privacy_pp = PrivacyMaskPP()

    print("流式输出: ", end="", flush=True)
    await prompt.acall(
        query="我的电话是 13800138000，张三的电话是 15912345678。请复述一遍。",
        is_stream=True,
        postprocessor=privacy_pp
    )
    print("\n\n[演示结束] 手机号被替换。")


# ============================================================
# 菜单逻辑
# ============================================================

async def main():
    menu = {
        "1": ("敏感词与竞品屏蔽 (ReplacePP)", example_sensitive_filter),
        "2": ("纯净代码提取 (PatternMatcherPP - Only)", example_code_extraction),
        "3": ("隐藏思维链/思考过程 (PatternMatcherPP - Exclude)", example_hide_thought),
        "4": ("JSON 字段定向提取 (JsonKeyExtractorPP)", example_json_field_stream),
        "5": ("链式组合处理 (Filter + Replace)", example_chain_processing),
        "6": ("自定义隐私掩码 (Custom Class)", example_custom_privacy),
    }

    while True:
        print("\n" + "=" * 50)
        print("      Alphora Prompter + PostProcess 进阶示例")
        print("=" * 50)
        for key, value in menu.items():
            print(f"[{key}] {value[0]}")
        print("[q] 退出程序")
        print("-" * 50)

        choice = input("请选择示例场景: ").strip().lower()

        if choice == 'q':
            print("退出。")
            break

        if choice in menu:
            try:
                await menu[choice][1]()
            except Exception as e:
                print(f"\n运行出错: {e}")
            input("\n按回车键继续...")
        else:
            print("无效输入，请重试。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
