"""
ExecutorAgent - 任务执行者

在沙箱中执行具体任务，通过工具调用完成编码、文件操作等工作。
具备自主记忆管理能力，在长链调用中自动压缩上下文。
"""

from alphora.agent.base_agent import BaseAgent
from alphora.tools.registry import ToolRegistry
from alphora.tools.executor import ToolExecutor
from alphora.sandbox import Sandbox, SandboxTools
from alphora.models.llms.types import ToolCall

from .memory_guard import MemoryGuard
from .prompts import EXECUTOR_SYSTEM, EXECUTOR_RUNTIME

from typing import Optional, Dict, List, Any
import json


class ExecutorAgent(BaseAgent):
    """
    执行者智能体 - 通过 Shell 和文件工具完成具体任务。
    
    Features:
    - 自动工具调用循环
    - 智能记忆压缩（通过 MemoryGuard）
    - 子任务状态追踪
    - 错误自恢复
    """
    agent_type = "ExecutorAgent"

    def __init__(
        self,
        sandbox: Sandbox,
        memory_guard: MemoryGuard,
        max_iterations: int = 50,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.sandbox = sandbox
        self.memory_guard = memory_guard
        self.max_iterations = max_iterations

    async def execute_task(
        self,
        task: Dict[str, Any],
        goal: str,
        quality_criteria: List[str],
        completed_tasks: List[str],
        revision_instructions: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        执行单个子任务。
        
        Args:
            task: 子任务定义 {"id", "title", "description"}
            goal: 总体目标
            quality_criteria: 质量标准列表
            completed_tasks: 已完成任务的描述列表
            revision_instructions: 审查者的修改指令（修订模式）
            
        Returns:
            {"status": "done"|"blocked", "message": str}
        """
        # 构建 Prompt
        executor_prompt = self.create_prompt(system_prompt=EXECUTOR_SYSTEM)

        # 构建工具集
        registry = ToolRegistry()
        executor = ToolExecutor(registry=registry)

        sb_tools = SandboxTools(self.sandbox)
        registry.register(sb_tools.run_shell_command)

        # 注册记忆压缩工具
        async def compress_memory() -> str:
            """压缩对话历史以释放上下文空间。在对话过长时调用。"""
            summary = await self.memory_guard.compress(sandbox=self.sandbox)
            return f"记忆已压缩。摘要: {summary[:200]}"

        registry.register(compress_memory)

        # 准备任务描述
        task_desc = f"[{task['id']}] {task['title']}\n{task['description']}"
        if revision_instructions:
            task_desc += f"\n\n⚠️ 审查者修改指令：\n{revision_instructions}"

        completed_str = "\n".join(
            f"✅ {t}" for t in completed_tasks
        ) if completed_tasks else "无"

        criteria_str = "\n".join(f"- {c}" for c in quality_criteria)

        # 添加用户消息
        self.memory_guard.add_user(
            f"请执行以下任务：\n{task_desc}"
        )

        # 执行循环
        for iteration in range(self.max_iterations):
            # 获取沙箱文件列表
            sandbox_files = await self.sandbox.list_files(recursive=True)

            # 更新动态变量
            executor_prompt.update_placeholder(
                goal=goal,
                current_task=task_desc,
                quality_criteria=criteria_str,
                completed_tasks=completed_str,
                sandbox_files=str(sandbox_files),
            )

            # 构建历史
            history = self.memory_guard.build_history(max_rounds=20)

            # 调用 LLM
            tc_resp: ToolCall = await executor_prompt.acall(
                history=history,
                is_stream=True,
                runtime_system_prompt=EXECUTOR_RUNTIME,
                tools=registry.get_openai_tools_schema(),
            )

            # 记录助手回复
            self.memory_guard.add_assistant(content=tc_resp)

            # 检查完成/阻塞信号
            resp_content = tc_resp.content or ""

            if "SUBTASK_DONE" in resp_content:
                return {
                    "status": "done",
                    "message": resp_content,
                    "iterations": iteration + 1,
                }

            if "SUBTASK_BLOCKED" in resp_content:
                return {
                    "status": "blocked",
                    "message": resp_content,
                    "iterations": iteration + 1,
                }

            # 处理工具调用
            if tc_resp.has_tool_calls:
                tool_return = await executor.execute(tool_calls=tc_resp)

                # compress_memory 工具调用后不记录结果（因为它会修改 memory）
                if "compress_memory" not in tc_resp.get_tool_names():
                    self.memory_guard.add_tool_result(result=tool_return)

                self.memory_guard.tick()

                # 自动检测是否需要压缩
                if self.memory_guard.should_compress():
                    await self.memory_guard.compress(sandbox=self.sandbox)

            else:
                # 无工具调用也无完成信号 -> 可能卡住了
                # 再给一次机会
                pass

        # 达到最大迭代次数
        return {
            "status": "done",
            "message": f"达到最大迭代次数 ({self.max_iterations})，强制结束。",
            "iterations": self.max_iterations,
        }
