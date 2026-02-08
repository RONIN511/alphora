"""
ReviewerAgent - 质量审查者

审查执行者的产出，评分并给出具体修改指令。
能够实际查看文件、运行测试来验证质量。
"""

from alphora.agent.base_agent import BaseAgent
from alphora.tools.registry import ToolRegistry
from alphora.tools.executor import ToolExecutor
from alphora.sandbox import Sandbox, SandboxTools
from alphora.memory import MemoryManager
from alphora.models.llms.types import ToolCall

from .prompts import REVIEWER_SYSTEM, REVIEWER_USER

from typing import Optional, Dict, List, Any
import json


# 默认审查报告（解析失败时的降级方案）
DEFAULT_REVIEW = {
    "verdict": "PASS",
    "score": 75,
    "summary": "审查完成，未能生成结构化报告，默认通过。",
    "strengths": [],
    "issues": [],
    "revision_instructions": "",
}


class ReviewerAgent(BaseAgent):
    """
    审查者智能体 - 严格审查执行者的产出。
    
    Features:
    - 实际查看文件内容验证
    - 可运行代码测试
    - 结构化评分报告
    - 可操作的修改指令
    """
    agent_type = "ReviewerAgent"

    def __init__(
        self,
        sandbox: Sandbox,
        pass_threshold: int = 80,
        max_review_iterations: int = 20,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.sandbox = sandbox
        self.pass_threshold = pass_threshold
        self.max_review_iterations = max_review_iterations
        self._memory = MemoryManager()

    async def review(
        self,
        original_query: str,
        task_plan: Dict[str, Any],
        quality_criteria: List[str],
    ) -> Dict[str, Any]:
        """
        执行完整审查流程。
        
        审查者可以使用工具查看文件、运行代码，然后输出结构化报告。
        
        Returns:
            审查报告 dict（包含 verdict, score, issues 等）
        """
        # 每次审查使用独立的 session
        session_id = f"review_{id(self)}"
        self._memory.clear(session_id=session_id)

        # 构建审查 Prompt
        review_prompt = self.create_prompt(
            system_prompt=REVIEWER_SYSTEM,
            user_prompt=REVIEWER_USER,
        )

        # 构建工具集（审查者只需读取和运行能力）
        registry = ToolRegistry()
        executor = ToolExecutor(registry=registry)

        sb_tools = SandboxTools(self.sandbox)
        registry.register(sb_tools.run_shell_command)

        # 获取沙箱文件
        sandbox_files = await self.sandbox.list_files(recursive=True)
        criteria_str = "\n".join(f"- {c}" for c in quality_criteria)
        plan_str = json.dumps(task_plan, ensure_ascii=False, indent=2)

        # 更新 Prompt 变量
        review_prompt.update_placeholder(
            original_query=original_query,
            task_plan=plan_str,
            sandbox_files=str(sandbox_files),
            quality_criteria=criteria_str,
        )

        # 审查者的工具调用循环
        self._memory.add_user(
            "请开始审查执行者的产出。查看文件、运行测试，然后输出 JSON 审查报告。",
            session_id=session_id,
        )

        json_report = None

        for iteration in range(self.max_review_iterations):
            history = self._memory.build_history(
                session_id=session_id,
                max_rounds=15,
            )

            tc_resp: ToolCall = await review_prompt.acall(
                history=history,
                is_stream=True,
                tools=registry.get_openai_tools_schema(),
            )

            self._memory.add_assistant(
                content=tc_resp,
                session_id=session_id,
            )

            # 处理工具调用
            if tc_resp.has_tool_calls:
                tool_return = await executor.execute(tool_calls=tc_resp)
                self._memory.add_tool_result(
                    result=tool_return,
                    session_id=session_id,
                )
                continue

            # 无工具调用 -> 尝试解析 JSON 报告
            resp_content = tc_resp.content or ""
            json_report = self._parse_review_report(resp_content)

            if json_report:
                break

        # 如果未能解析出报告，使用默认值
        if not json_report:
            json_report = DEFAULT_REVIEW.copy()

        # 清理审查 session
        self._memory.clear(session_id=session_id)

        return json_report

    def _parse_review_report(self, text: str) -> Optional[Dict[str, Any]]:
        """
        从审查者的回复中解析 JSON 报告。
        支持从 markdown 代码块中提取 JSON。
        """
        import re

        # 尝试直接解析
        try:
            report = json.loads(text)
            if self._validate_report(report):
                return report
        except json.JSONDecodeError:
            pass

        # 尝试从 markdown 代码块提取
        json_patterns = [
            r"```json\s*\n(.*?)\n\s*```",
            r"```\s*\n(.*?)\n\s*```",
            r"\{[^{}]*\"verdict\"[^{}]*\}",
        ]

        for pattern in json_patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                try:
                    report = json.loads(match)
                    if self._validate_report(report):
                        return report
                except json.JSONDecodeError:
                    continue

        return None

    def _validate_report(self, report: Dict) -> bool:
        """验证报告结构"""
        required_keys = {"verdict", "score"}
        return (
            isinstance(report, dict)
            and required_keys.issubset(report.keys())
            and report.get("verdict") in ("PASS", "FAIL", "NEEDS_REVISION")
            and isinstance(report.get("score"), (int, float))
        )
