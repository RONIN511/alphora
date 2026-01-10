"""
长响应模块 - 自动续写超长内容
"""

import logging
from typing import Optional, AsyncIterator, Iterator

from alphora.models.llms.stream_helper import BaseGenerator, GeneratorOutput
from alphora.models.message import Message

logger = logging.getLogger(__name__)


SYSTEM_ENHANCEMENT = """
【指令：深度长文模式】

你现在处于"长内容生成模式"。请严格遵守以下规则：

1. **忽略篇幅限制**：不需要考虑输出长度，不需要为了节省字数而精简内容。
2. **拒绝过渡总结**：严禁使用"综上所述"、"由于篇幅"、"后续将介绍"等截断性语句，除非内容逻辑通过自然结束。
3. **保持原子性**：如果系统提示你继续，意味着你上一句话可能没说完。请保持上下文的连贯性，就像你的手从未离开键盘一样。
4. **格式完整**：在生成代码、列表或数学公式时，即使遇到截断，也不要试图手动闭合标签，系统会处理拼接。

目标：提供详尽、完整、未经压缩的专家级内容。
"""


CONTINUATION_PROMPT = """【系统中断 - 自动续写指令】

**任务背景**：
{original_task}

**当前状态**：
你的输出因长度限制被截断。请紧接下文继续生成，**实现字符级的无缝拼接**。

**截断前的最后内容（Context）**：
...
{tail_content}
>>>

**续写要求**：
1. **严禁重复**：绝对不要重复"截断前的最后内容"中的任何文字。
2. **严禁废话**：不要输出"接上文"、"继续"、"好的"等开场白。
3. **格式延续**：如果截断处处于代码块、Markdown列表或公式中，请直接输出后续内容，**不要**重新打印 ```代码块标记 或 列表符号。
4. **立即开始**：直接输出截断处的下一个字符。

请继续："""


class LongResponseGenerator(BaseGenerator[GeneratorOutput]):
    """长响应生成器"""

    def __init__(
            self,
            llm,
            original_message: Message,
            content_type: str = 'char',
            system_prompt: Optional[str] = None,
            enable_thinking: bool = False,
    ):
        super().__init__(content_type)
        self.llm = llm
        self.original_message = original_message
        self.system_prompt = system_prompt
        self.enable_thinking = enable_thinking

        self.max_continuations = 100
        self.tail_length = 1500
        self.min_chunk_length = 50

        self.accumulated_content = ""
        self.continuation_count = 0

        self._original_task = self._extract_task(original_message)

    def _extract_task(self, message: Message) -> str:
        try:
            if hasattr(message, 'content'):
                if isinstance(message.content, str):
                    return message.content
                elif isinstance(message.content, list):
                    texts = []
                    for item in message.content:
                        if isinstance(item, dict) and item.get('type') == 'text':
                            texts.append(item.get('text', ''))
                        elif isinstance(item, str):
                            texts.append(item)
                    return '\n'.join(texts)
            return str(message)
        except:
            return str(message)

    def _build_continuation_message(self) -> Message:
        tail = self.accumulated_content[-self.tail_length:] if len(self.accumulated_content) > self.tail_length else self.accumulated_content

        prompt = CONTINUATION_PROMPT.format(
            original_task=self._original_task[:2000],
            written_length=len(self.accumulated_content),
            tail_content=tail
        )

        msg = Message()
        msg.add_text(prompt)
        return msg

    def _get_enhanced_system(self) -> str:
        base = self.system_prompt or ""
        return f"{base}\n\n{SYSTEM_ENHANCEMENT}".strip()

    async def agenerate(self) -> AsyncIterator[GeneratorOutput]:
        current_message = self.original_message

        while self.continuation_count <= self.max_continuations:
            sys_prompt = self._get_enhanced_system()

            generator = await self.llm.aget_streaming_response(
                message=current_message,
                content_type=self.content_type,
                enable_thinking=self.enable_thinking,
                system_prompt=sys_prompt
            )

            chunk_content = ""

            async for output in generator:
                if output.content_type == 'think':
                    yield output
                    continue

                chunk_content += output.content
                self.accumulated_content += output.content

                if output.content:
                    yield GeneratorOutput(content=output.content, content_type=output.content_type)

            finish_reason = getattr(generator, 'finish_reason', 'stop')

            logger.info(
                f"[第{self.continuation_count}次] "
                f"finish_reason={finish_reason}, "
                f"本次={len(chunk_content)}字, "
                f"累计={len(self.accumulated_content)}字"
            )

            if finish_reason == 'length':
                if len(chunk_content) < self.min_chunk_length:
                    logger.warning(f"输出过短，停止")
                    break

                self.continuation_count += 1
                current_message = self._build_continuation_message()
                logger.info(f"→ 续写")
            else:
                break

        self.finish_reason = 'stop'

    def generate(self) -> Iterator[GeneratorOutput]:
        current_message = self.original_message

        while self.continuation_count <= self.max_continuations:
            sys_prompt = self._get_enhanced_system()

            generator = self.llm.get_streaming_response(
                message=current_message,
                content_type=self.content_type,
                enable_thinking=self.enable_thinking,
                system_prompt=sys_prompt
            )

            chunk_content = ""

            for output in generator:
                if output.content_type == 'think':
                    yield output
                    continue

                chunk_content += output.content
                self.accumulated_content += output.content

                if output.content:
                    yield GeneratorOutput(content=output.content, content_type=output.content_type)

            finish_reason = getattr(generator, 'finish_reason', 'stop')

            logger.info(
                f"[第{self.continuation_count}次] "
                f"finish_reason={finish_reason}, "
                f"本次={len(chunk_content)}字, "
                f"累计={len(self.accumulated_content)}字"
            )

            if finish_reason == 'length':
                if len(chunk_content) < self.min_chunk_length:
                    logger.warning(f"输出过短，停止")
                    break

                self.continuation_count += 1
                current_message = self._build_continuation_message()
                logger.info(f"→ 续写")
            else:
                break

        self.finish_reason = 'stop'

