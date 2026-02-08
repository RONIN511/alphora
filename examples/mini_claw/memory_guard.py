"""
MemoryGuard - 智能记忆管理器

解决长链调用中的上下文膨胀问题。
采用分层策略：Pin 关键信息 + 定期压缩 + LLM 摘要。
"""

from alphora.memory import MemoryManager
from alphora.memory.processors import (
    chain, keep_last, truncate_content,
    remove_tool_details, keep_pinned, keep_important_and_last,
)
from alphora.prompter import BasePrompt
from alphora.models import OpenAILike

from .prompts import SUMMARIZER_SYSTEM, SUMMARIZER_USER

from typing import Optional, List, Dict, Any


class MemoryGuard:
    """
    智能记忆管理器，为长链 Agent 调用提供记忆压缩与管理。
    
    策略:
    1. 关键消息自动 Pin（任务计划、审查报告、里程碑）
    2. 工具调用结果按新鲜度衰减（旧的结果被摘要替代）
    3. 超过阈值时触发 LLM 摘要压缩
    4. 进展日志持久化到沙箱文件系统
    """

    def __init__(
        self,
        memory: MemoryManager,
        llm: Optional[OpenAILike] = None,
        max_rounds_before_compress: int = 15,
        keep_recent_rounds: int = 8,
        max_content_length: int = 3000,
        session_id: str = "default",
    ):
        self.memory = memory
        self.llm = llm
        self.max_rounds_before_compress = max_rounds_before_compress
        self.keep_recent_rounds = keep_recent_rounds
        self.max_content_length = max_content_length
        self.session_id = session_id

        self._round_counter = 0
        self._compression_count = 0
        self._summaries: List[str] = []  # 历次压缩的摘要

    @property
    def round_counter(self) -> int:
        return self._round_counter

    def tick(self):
        """每完成一轮工具调用后调用，递增计数器"""
        self._round_counter += 1

    def should_compress(self) -> bool:
        """判断是否需要触发压缩"""
        return self._round_counter >= self.max_rounds_before_compress

    def pin_message(self, content: str, tag: str = "milestone"):
        """Pin 一条关键消息（如任务计划、审查结果）"""
        self.memory.add_system(
            content=content,
            session_id=self.session_id,
        )
        # 获取刚添加的最后一条消息并 pin + tag
        last_msg = self.memory.get_last_message(session_id=self.session_id)
        if last_msg:
            self.memory.pin(last_msg.id, session_id=self.session_id)
            self.memory.tag(tag, last_msg.id, session_id=self.session_id)

    async def compress(self, sandbox=None) -> str:
        """
        执行智能压缩：
        1. 用 LLM 总结即将被丢弃的旧消息
        2. 将摘要注入为 pinned system message
        3. 压缩历史，保留最近 N 轮 + pinned 消息
        4. 可选：将进展写入沙箱文件
        
        Returns:
            压缩摘要文本
        """
        summary_text = ""

        # 获取所有消息用于生成摘要
        all_messages = self.memory.get_messages(session_id=self.session_id)

        if self.llm and len(all_messages) > self.keep_recent_rounds * 2:
            summary_text = await self._generate_summary(all_messages)
        else:
            # 无 LLM 时使用简单规则摘要
            summary_text = self._rule_based_summary(all_messages)

        # 执行压缩
        self.memory.compress(
            session_id=self.session_id,
            keep_rounds=self.keep_recent_rounds,
            keep_pinned=True,
            keep_tagged=["milestone", "plan", "review"],
        )

        # 注入压缩摘要作为 pinned 消息
        if summary_text:
            self.pin_message(
                f"[历史摘要 #{self._compression_count + 1}]\n{summary_text}",
                tag="summary",
            )
            self._summaries.append(summary_text)

        # 持久化进展到文件
        if sandbox:
            await self._persist_progress(sandbox, summary_text)

        self._compression_count += 1
        self._round_counter = 0  # 重置计数器

        return summary_text

    def build_history(self, max_rounds: int = 20):
        """
        构建经过优化的历史记录，用于传给 LLM。
        应用处理器链：保留 pinned + 最近消息 + 截断长内容。
        """
        return self.memory.build_history(
            session_id=self.session_id,
            max_rounds=max_rounds,
            keep_pinned=True,
            keep_tagged=["milestone", "plan", "review", "summary"],
            processor=chain(
                truncate_content(max_length=self.max_content_length),
            ),
        )

    def add_user(self, content: str):
        self.memory.add_user(content=content, session_id=self.session_id)

    def add_assistant(self, content):
        self.memory.add_assistant(content=content, session_id=self.session_id)

    def add_tool_result(self, result):
        self.memory.add_tool_result(result=result, session_id=self.session_id)

    def clear(self):
        self.memory.clear(session_id=self.session_id)
        self._round_counter = 0

    async def _generate_summary(self, messages) -> str:
        """使用 LLM 生成对话摘要"""
        try:
            # 将消息转为文本
            conversation_parts = []
            for msg in messages:
                role = msg.role.upper() if hasattr(msg, 'role') else 'UNKNOWN'
                content = msg.content or ''
                if len(content) > 500:
                    content = content[:500] + '...(truncated)'
                conversation_parts.append(f"[{role}]: {content}")

            conversation_text = "\n".join(conversation_parts[-30:])  # 最多取最近30条

            prompt = BasePrompt(
                system_prompt=SUMMARIZER_SYSTEM,
                user_prompt=SUMMARIZER_USER,
            )
            prompt.add_llm(self.llm)

            response = await prompt.acall(
                conversation_text=conversation_text,
                is_stream=False,
            )
            return str(response)

        except Exception as e:
            # 降级为规则摘要
            return self._rule_based_summary(messages)

    def _rule_based_summary(self, messages) -> str:
        """规则型摘要（LLM 不可用时的降级方案）"""
        parts = []
        tool_calls_count = 0
        errors = []

        for msg in messages:
            content = msg.content or ""
            if hasattr(msg, 'role'):
                if msg.role == "tool":
                    tool_calls_count += 1
                    if "error" in content.lower() or "Error" in content:
                        errors.append(content[:100])
                elif msg.role == "assistant" and (
                    "SUBTASK_DONE" in content or "TASK_FINISHED" in content
                ):
                    parts.append(f"- {content[:200]}")

        summary = f"执行了 {tool_calls_count} 次工具调用。"
        if parts:
            summary += "\n关键进展：\n" + "\n".join(parts[-5:])
        if errors:
            summary += f"\n遇到 {len(errors)} 个错误。"

        return summary

    async def _persist_progress(self, sandbox, summary: str):
        """将进展追加写入沙箱文件"""
        try:
            progress_entry = (
                f"\n\n---\n"
                f"## 压缩记录 #{self._compression_count + 1}\n"
                f"{summary}\n"
            )
            # 使用 shell 追加写入
            await sandbox.execute_shell(
                f"echo {repr(progress_entry)} >> PROGRESS.md"
            )
        except Exception:
            pass  # 非关键操作，静默失败
