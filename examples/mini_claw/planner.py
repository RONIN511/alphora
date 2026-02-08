"""
PlannerAgent - 任务规划与分解

将复杂用户需求拆解为可执行的子任务序列。
"""

from alphora.agent.base_agent import BaseAgent
from alphora.prompter import BasePrompt
from alphora.sandbox import Sandbox

from .prompts import PLANNER_SYSTEM, PLANNER_USER

from typing import Dict, Any, Optional
import json
import re


class PlannerAgent(BaseAgent):
    """
    规划者智能体 - 将复杂需求分解为子任务。
    
    Features:
    - 自动分析需求复杂度
    - 生成带依赖关系的子任务序列
    - 定义可验证的质量标准
    """
    agent_type = "PlannerAgent"

    def __init__(self, sandbox: Sandbox, **kwargs):
        super().__init__(**kwargs)
        self.sandbox = sandbox

    async def plan(self, query: str) -> Dict[str, Any]:
        """
        分析用户需求并生成任务计划。
        
        Returns:
            任务计划字典，包含 tasks, quality_criteria 等
        """
        planner_prompt = self.create_prompt(
            system_prompt=PLANNER_SYSTEM,
            user_prompt=PLANNER_USER,
        )

        # 获取沙箱当前状态
        sandbox_files = await self.sandbox.list_files(recursive=True)

        planner_prompt.update_placeholder(sandbox_files=str(sandbox_files))

        response = await planner_prompt.acall(
            query=query,
            is_stream=False,
            force_json=True,
        )

        # 解析计划
        plan = self._parse_plan(str(response))

        if not plan:
            # 降级：生成单任务计划
            plan = self._fallback_plan(query)

        return plan

    def _parse_plan(self, text: str) -> Optional[Dict[str, Any]]:
        """从 LLM 输出中解析任务计划"""
        # 尝试直接解析
        try:
            plan = json.loads(text)
            if self._validate_plan(plan):
                return plan
        except json.JSONDecodeError:
            pass

        # 尝试从 markdown 提取
        patterns = [
            r"```json\s*\n(.*?)\n\s*```",
            r"```\s*\n(.*?)\n\s*```",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                try:
                    plan = json.loads(match)
                    if self._validate_plan(plan):
                        return plan
                except json.JSONDecodeError:
                    continue

        return None

    def _validate_plan(self, plan: Dict) -> bool:
        """验证计划结构"""
        return (
            isinstance(plan, dict)
            and "tasks" in plan
            and isinstance(plan["tasks"], list)
            and len(plan["tasks"]) > 0
        )

    def _fallback_plan(self, query: str) -> Dict[str, Any]:
        """降级方案：将整个需求作为单个任务"""
        return {
            "goal": query[:200],
            "analysis": "无法自动分解，作为单个任务执行。",
            "tasks": [
                {
                    "id": "task_001",
                    "title": "执行用户需求",
                    "description": query,
                    "depends_on": [],
                    "priority": "high",
                    "estimated_complexity": "complex",
                }
            ],
            "quality_criteria": [
                "功能完整：满足用户描述的所有需求",
                "代码质量：结构清晰、有适当注释",
                "可运行：代码无语法错误，可正常执行",
            ],
            "file_structure": "由执行者自行决定",
        }
