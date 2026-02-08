"""
EvolutionEngine - 自进化引擎

核心编排器，驱动 Planner → Executor → Reviewer 的自进化循环。
每个子任务经过 执行→审查→修订 的闭环，直到达到质量标准。

流程:
    1. Planner 分解任务
    2. 对每个子任务:
       a. Executor 执行
       b. Reviewer 审查
       c. 如果未通过 → 带着修改指令回到 Executor（最多 N 轮）
       d. 通过 → 进入下一个子任务
    3. 最终全局审查
"""

from alphora.agent.base_agent import BaseAgent
from alphora.models import OpenAILike
from alphora.memory import MemoryManager
from alphora.sandbox import Sandbox, StorageConfig, LocalStorage

from .planner import PlannerAgent
from .executor import ExecutorAgent
from .reviewer import ReviewerAgent
from .memory_guard import MemoryGuard

from typing import Optional, Dict, List, Any, Callable
import json
import time


class TaskResult:
    """单个子任务的执行结果"""

    def __init__(self, task_id: str, task_title: str):
        self.task_id = task_id
        self.task_title = task_title
        self.attempts: List[Dict] = []  # 每次尝试的记录
        self.final_status: str = "pending"  # done, blocked, max_retries
        self.final_review: Optional[Dict] = None
        self.total_iterations: int = 0

    def add_attempt(self, exec_result: Dict, review: Optional[Dict]):
        self.attempts.append({
            "execution": exec_result,
            "review": review,
            "timestamp": time.time(),
        })
        self.total_iterations += exec_result.get("iterations", 0)

    @property
    def passed(self) -> bool:
        return (
            self.final_review is not None
            and self.final_review.get("verdict") == "PASS"
        )


class EvolutionReport:
    """整体执行报告"""

    def __init__(self, query: str, plan: Dict):
        self.query = query
        self.plan = plan
        self.task_results: List[TaskResult] = []
        self.final_review: Optional[Dict] = None
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.total_iterations = 0

    @property
    def duration(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time

    @property
    def success(self) -> bool:
        return all(r.passed or r.final_status == "done" for r in self.task_results)

    def summary(self) -> str:
        lines = [
            f"═══ Evolution Report ═══",
            f"目标: {self.query[:100]}",
            f"耗时: {self.duration:.1f}s",
            f"总迭代: {self.total_iterations}",
            f"",
            f"子任务结果:",
        ]
        for r in self.task_results:
            status_icon = "✅" if r.passed else ("⚠️" if r.final_status == "done" else "❌")
            score = r.final_review.get("score", "N/A") if r.final_review else "N/A"
            lines.append(
                f"  {status_icon} [{r.task_id}] {r.task_title} "
                f"(尝试: {len(r.attempts)}, 迭代: {r.total_iterations}, 分数: {score})"
            )

        if self.final_review:
            lines.extend([
                f"",
                f"最终审查: {self.final_review.get('verdict', 'N/A')} "
                f"({self.final_review.get('score', 'N/A')}分)",
                f"  {self.final_review.get('summary', '')}",
            ])

        return "\n".join(lines)


class EvolutionEngine:
    """
    自进化引擎 - 驱动 Plan → Execute → Review 的闭环。
    
    Architecture:
        EvolutionEngine
        ├── PlannerAgent     (分解任务)
        ├── ExecutorAgent    (执行任务)
        │   └── MemoryGuard  (记忆管理)
        └── ReviewerAgent    (审查质量)
    
    Usage:
        engine = EvolutionEngine(
            llm=OpenAILike(model_name="qwen-max"),
            sandbox=sandbox,
        )
        report = await engine.run("做一个贪吃蛇游戏")
        print(report.summary())
    """

    def __init__(
        self,
        llm: OpenAILike,
        sandbox: Sandbox,
        reviewer_llm: Optional[OpenAILike] = None,
        max_revisions_per_task: int = 3,
        pass_threshold: int = 80,
        skip_planning: bool = False,
        on_progress: Optional[Callable] = None,
        verbose: bool = True,
    ):
        """
        Args:
            llm: 主 LLM（用于 Planner 和 Executor）
            sandbox: 沙箱实例
            reviewer_llm: 审查者 LLM（默认与主 LLM 相同，但建议用不同模型增加多样性）
            max_revisions_per_task: 每个子任务最大修订次数
            pass_threshold: 审查通过分数阈值
            skip_planning: 跳过规划阶段（直接作为单任务执行）
            on_progress: 进度回调 fn(event: str, data: dict)
            verbose: 详细输出
        """
        self.llm = llm
        self.sandbox = sandbox
        self.reviewer_llm = reviewer_llm or llm
        self.max_revisions = max_revisions_per_task
        self.pass_threshold = pass_threshold
        self.skip_planning = skip_planning
        self.on_progress = on_progress
        self.verbose = verbose

    async def run(self, query: str) -> EvolutionReport:
        """
        执行完整的自进化流程。
        
        Args:
            query: 用户需求描述
            
        Returns:
            EvolutionReport 完整执行报告
        """
        self._log(f"\n{'='*60}")
        self._log(f"🚀 Evolution Engine 启动")
        self._log(f"   需求: {query[:100]}")
        self._log(f"{'='*60}\n")

        # ─── Phase 1: 规划 ───
        self._emit("planning_start", {"query": query})
        plan = await self._plan(query)
        self._emit("planning_done", {"plan": plan})

        report = EvolutionReport(query=query, plan=plan)

        tasks = plan.get("tasks", [])
        quality_criteria = plan.get("quality_criteria", [])
        goal = plan.get("goal", query[:200])

        self._log(f"📋 任务计划: {len(tasks)} 个子任务")
        for t in tasks:
            self._log(f"   - [{t['id']}] {t['title']}")

        # ─── Phase 2: 逐任务执行-审查循环 ───
        completed_tasks: List[str] = []

        for task_idx, task in enumerate(tasks):
            self._log(f"\n{'─'*50}")
            self._log(f"📌 子任务 {task_idx+1}/{len(tasks)}: [{task['id']}] {task['title']}")
            self._log(f"{'─'*50}")

            task_result = TaskResult(
                task_id=task["id"],
                task_title=task["title"],
            )

            revision_instructions = None

            for attempt in range(self.max_revisions + 1):
                is_revision = attempt > 0
                if is_revision:
                    self._log(f"\n🔄 修订尝试 #{attempt} (审查者反馈: {revision_instructions[:100]}...)")

                self._emit("task_execute_start", {
                    "task": task,
                    "attempt": attempt,
                    "is_revision": is_revision,
                })

                # ── 执行 ──
                exec_result = await self._execute_task(
                    task=task,
                    goal=goal,
                    quality_criteria=quality_criteria,
                    completed_tasks=completed_tasks,
                    revision_instructions=revision_instructions,
                )

                self._log(f"   执行完成: {exec_result['status']} ({exec_result.get('iterations', '?')} 轮)")

                # ── 审查 ──
                if exec_result["status"] == "blocked":
                    task_result.add_attempt(exec_result, None)
                    task_result.final_status = "blocked"
                    self._log(f"   ⚠️ 任务被阻塞: {exec_result.get('message', '')[:100]}")
                    break

                self._emit("task_review_start", {"task": task, "attempt": attempt})

                review = await self._review(
                    original_query=query,
                    task_plan=plan,
                    quality_criteria=quality_criteria,
                )

                task_result.add_attempt(exec_result, review)

                score = review.get("score", 0)
                verdict = review.get("verdict", "FAIL")

                self._log(f"   审查结果: {verdict} ({score}分)")
                if review.get("summary"):
                    self._log(f"   摘要: {review['summary'][:100]}")

                self._emit("task_review_done", {
                    "task": task,
                    "attempt": attempt,
                    "review": review,
                })

                # ── 判定 ──
                if verdict == "PASS" or score >= self.pass_threshold:
                    task_result.final_status = "done"
                    task_result.final_review = review
                    self._log(f"   ✅ 通过!")
                    break

                if attempt < self.max_revisions:
                    # 准备修订指令
                    revision_instructions = review.get(
                        "revision_instructions",
                        self._build_revision_instructions(review),
                    )
                else:
                    # 已达最大修订次数
                    task_result.final_status = "max_retries"
                    task_result.final_review = review
                    self._log(f"   ⚠️ 达到最大修订次数，继续下一个任务")

            report.task_results.append(task_result)
            report.total_iterations += task_result.total_iterations
            completed_tasks.append(f"[{task['id']}] {task['title']}")

        # ─── Phase 3: 最终全局审查 ───
        self._log(f"\n{'='*60}")
        self._log(f"🔍 最终全局审查...")
        self._log(f"{'='*60}")

        final_review = await self._review(
            original_query=query,
            task_plan=plan,
            quality_criteria=quality_criteria,
        )
        report.final_review = final_review
        report.end_time = time.time()

        self._log(f"\n{report.summary()}")
        self._emit("completed", {"report": report.summary()})

        return report

    async def _plan(self, query: str) -> Dict[str, Any]:
        """规划阶段"""
        if self.skip_planning:
            return PlannerAgent(
                sandbox=self.sandbox, llm=self.llm
            )._fallback_plan(query)

        planner = PlannerAgent(
            sandbox=self.sandbox,
            llm=self.llm,
            verbose=self.verbose,
        )
        return await planner.plan(query)

    async def _execute_task(
        self,
        task: Dict,
        goal: str,
        quality_criteria: List[str],
        completed_tasks: List[str],
        revision_instructions: Optional[str],
    ) -> Dict[str, Any]:
        """执行阶段 - 每个子任务创建独立的 executor + memory"""
        memory = MemoryManager()
        memory_guard = MemoryGuard(
            memory=memory,
            llm=self.llm,
            session_id=f"exec_{task['id']}",
            max_rounds_before_compress=12,
            keep_recent_rounds=6,
        )

        executor = ExecutorAgent(
            sandbox=self.sandbox,
            memory_guard=memory_guard,
            llm=self.llm,
            verbose=self.verbose,
            max_iterations=50,
        )

        return await executor.execute_task(
            task=task,
            goal=goal,
            quality_criteria=quality_criteria,
            completed_tasks=completed_tasks,
            revision_instructions=revision_instructions,
        )

    async def _review(
        self,
        original_query: str,
        task_plan: Dict,
        quality_criteria: List[str],
    ) -> Dict[str, Any]:
        """审查阶段"""
        reviewer = ReviewerAgent(
            sandbox=self.sandbox,
            llm=self.reviewer_llm,
            verbose=self.verbose,
            pass_threshold=self.pass_threshold,
        )

        return await reviewer.review(
            original_query=original_query,
            task_plan=task_plan,
            quality_criteria=quality_criteria,
        )

    def _build_revision_instructions(self, review: Dict) -> str:
        """从审查报告中提取修订指令"""
        parts = []
        issues = review.get("issues", [])

        for issue in issues:
            severity = issue.get("severity", "unknown")
            desc = issue.get("description", "")
            fix = issue.get("fix_suggestion", "")
            location = issue.get("location", "")

            part = f"[{severity.upper()}]"
            if location:
                part += f" ({location})"
            part += f" {desc}"
            if fix:
                part += f" → 建议修复: {fix}"

            parts.append(part)

        if not parts:
            return review.get("summary", "请根据审查反馈进行修改。")

        return "请修复以下问题：\n" + "\n".join(parts)

    def _log(self, message: str):
        if self.verbose:
            print(message)

    def _emit(self, event: str, data: Dict):
        if self.on_progress:
            try:
                self.on_progress(event, data)
            except Exception:
                pass
