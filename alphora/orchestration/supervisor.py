"""
Supervisor 编排器 - 监督者模式

特性：
1. 一个主Agent监督多个子Agent
2. 主Agent决定任务分配
3. 支持任务迭代和反馈
4. 支持多轮对话协调
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union, Awaitable
from enum import Enum

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_REVISION = "needs_revision"


@dataclass
class WorkerAgent:
    """工作Agent定义"""
    name: str
    handler: Callable[..., Awaitable[Any]]
    description: str = ""
    capabilities: List[str] = field(default_factory=list)
    max_concurrent_tasks: int = 1
    current_tasks: int = 0
    
    @property
    def available(self) -> bool:
        """是否可接受新任务"""
        return self.current_tasks < self.max_concurrent_tasks


@dataclass
class Task:
    """任务定义"""
    id: str
    description: str
    assigned_to: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    input_data: Dict[str, Any] = field(default_factory=dict)
    output: Any = None
    feedback: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 3
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "assigned_to": self.assigned_to,
            "status": self.status.value,
            "output": self.output,
            "feedback": self.feedback,
            "attempts": self.attempts
        }


@dataclass
class SupervisorConfig:
    """Supervisor配置"""
    max_iterations: int = 10  # 最大迭代次数
    require_approval: bool = False  # 是否需要人工审批
    allow_parallel: bool = True  # 是否允许并行执行
    feedback_enabled: bool = True  # 是否启用反馈机制
    auto_retry: bool = True  # 是否自动重试失败任务


class Supervisor:
    """
    Supervisor 编排器
    
    一个监督者Agent协调多个工作Agent完成复杂任务。
    
    使用示例：
    ```python
    # 创建Supervisor
    supervisor = Supervisor(
        name="project_manager",
        llm=llm,
        config=SupervisorConfig(max_iterations=5)
    )
    
    # 注册工作Agent
    supervisor.register_worker(WorkerAgent(
        name="researcher",
        handler=research_agent.research,
        description="负责信息收集和研究",
        capabilities=["search", "summarize"]
    ))
    
    supervisor.register_worker(WorkerAgent(
        name="writer",
        handler=writer_agent.write,
        description="负责撰写内容",
        capabilities=["write", "edit"]
    ))
    
    # 执行复杂任务
    result = await supervisor.execute(
        goal="写一篇关于AI发展的研究报告",
        context={"format": "markdown", "length": "2000字"}
    )
    ```
    """
    
    PLANNING_PROMPT = """你是一个项目经理，需要协调团队完成任务。

目标: {goal}
上下文: {context}

可用的团队成员:
{workers}

当前任务状态:
{task_status}

请分析当前情况并决定下一步行动。返回JSON格式:
{{
    "action": "assign_task" | "request_revision" | "complete" | "need_more_info",
    "tasks": [
        {{
            "worker": "工作者名称",
            "description": "任务描述",
            "input": {{}}
        }}
    ],
    "reasoning": "决策理由",
    "final_output": "如果action是complete，这里是最终输出"
}}
"""

    REVIEW_PROMPT = """你是一个项目经理，需要审核任务完成情况。

原始目标: {goal}
任务: {task_description}
工作者: {worker_name}
输出结果: {output}

请评估任务完成质量，返回JSON格式:
{{
    "approved": true | false,
    "feedback": "反馈意见",
    "needs_revision": true | false
}}
"""
    
    def __init__(
        self,
        name: str = "supervisor",
        llm: Optional[Any] = None,
        config: Optional[SupervisorConfig] = None,
        planning_prompt: Optional[str] = None,
        review_prompt: Optional[str] = None
    ):
        self.name = name
        self.llm = llm
        self.config = config or SupervisorConfig()
        self.planning_prompt = planning_prompt or self.PLANNING_PROMPT
        self.review_prompt = review_prompt or self.REVIEW_PROMPT
        
        self.workers: Dict[str, WorkerAgent] = {}
        self.tasks: Dict[str, Task] = {}
        self.task_counter = 0
        self.iteration = 0
    
    def register_worker(self, worker: WorkerAgent) -> "Supervisor":
        """注册工作Agent"""
        self.workers[worker.name] = worker
        logger.info(f"Registered worker: {worker.name}")
        return self
    
    def unregister_worker(self, name: str) -> bool:
        """注销工作Agent"""
        if name in self.workers:
            del self.workers[name]
            return True
        return False
    
    def _create_task(self, description: str, input_data: Dict[str, Any] = None) -> Task:
        """创建新任务"""
        self.task_counter += 1
        task = Task(
            id=f"task_{self.task_counter}",
            description=description,
            input_data=input_data or {}
        )
        self.tasks[task.id] = task
        return task
    
    def _get_workers_info(self) -> str:
        """获取工作者信息"""
        info = []
        for name, worker in self.workers.items():
            status = "可用" if worker.available else "忙碌"
            info.append(
                f"- {name}: {worker.description} "
                f"[能力: {', '.join(worker.capabilities)}] [{status}]"
            )
        return "\n".join(info)
    
    def _get_task_status(self) -> str:
        """获取任务状态"""
        if not self.tasks:
            return "暂无任务"
        
        info = []
        for task_id, task in self.tasks.items():
            info.append(
                f"- {task_id}: {task.description} "
                f"[{task.status.value}] "
                f"[执行者: {task.assigned_to or '未分配'}]"
            )
            if task.output:
                output_preview = str(task.output)[:100] + "..." if len(str(task.output)) > 100 else str(task.output)
                info.append(f"  输出: {output_preview}")
            if task.feedback:
                info.append(f"  反馈: {task.feedback}")
        
        return "\n".join(info)
    
    async def _plan(self, goal: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """规划下一步行动"""
        if not self.llm:
            raise ValueError("LLM is required for planning")
        
        prompt = self.planning_prompt.format(
            goal=goal,
            context=json.dumps(context, ensure_ascii=False),
            workers=self._get_workers_info(),
            task_status=self._get_task_status()
        )
        
        try:
            response = await self.llm.ainvoke(prompt)
            # 尝试解析JSON
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            
            return json.loads(response)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse planning response: {response}")
            return {"action": "need_more_info", "reasoning": "无法解析规划结果"}
    
    async def _review_output(
        self,
        goal: str,
        task: Task,
        output: Any
    ) -> Dict[str, Any]:
        """审核任务输出"""
        if not self.llm or not self.config.feedback_enabled:
            return {"approved": True, "feedback": "", "needs_revision": False}
        
        prompt = self.review_prompt.format(
            goal=goal,
            task_description=task.description,
            worker_name=task.assigned_to,
            output=str(output)[:2000]  # 限制长度
        )
        
        try:
            response = await self.llm.ainvoke(prompt)
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            
            return json.loads(response)
        except json.JSONDecodeError:
            return {"approved": True, "feedback": "", "needs_revision": False}
    
    async def _execute_task(self, task: Task) -> Any:
        """执行单个任务"""
        worker = self.workers.get(task.assigned_to)
        if not worker:
            raise ValueError(f"Worker '{task.assigned_to}' not found")
        
        worker.current_tasks += 1
        task.status = TaskStatus.IN_PROGRESS
        task.attempts += 1
        
        try:
            result = await worker.handler(
                task=task.description,
                input_data=task.input_data,
                feedback=task.feedback
            )
            return result
        finally:
            worker.current_tasks -= 1
    
    async def execute(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        on_iteration: Optional[Callable[[int, Dict], None]] = None
    ) -> Dict[str, Any]:
        """
        执行监督任务
        
        Args:
            goal: 任务目标
            context: 上下文信息
            on_iteration: 每次迭代的回调
        
        Returns:
            执行结果
        """
        context = context or {}
        self.iteration = 0
        self.tasks.clear()
        
        logger.info(f"Supervisor '{self.name}' starting execution: {goal}")
        
        while self.iteration < self.config.max_iterations:
            self.iteration += 1
            logger.info(f"Iteration {self.iteration}/{self.config.max_iterations}")
            
            # 规划
            plan = await self._plan(goal, context)
            
            if on_iteration:
                on_iteration(self.iteration, plan)
            
            action = plan.get("action", "")
            
            # 处理不同的行动
            if action == "complete":
                logger.info("Supervisor completed task")
                return {
                    "status": "completed",
                    "output": plan.get("final_output"),
                    "iterations": self.iteration,
                    "tasks": [t.to_dict() for t in self.tasks.values()]
                }
            
            elif action == "assign_task":
                # 分配并执行任务
                tasks_to_execute = plan.get("tasks", [])
                
                if self.config.allow_parallel:
                    # 并行执行
                    execution_tasks = []
                    for task_info in tasks_to_execute:
                        task = self._create_task(
                            description=task_info["description"],
                            input_data=task_info.get("input", {})
                        )
                        task.assigned_to = task_info["worker"]
                        task.status = TaskStatus.ASSIGNED
                        execution_tasks.append(self._execute_task(task))
                    
                    if execution_tasks:
                        results = await asyncio.gather(*execution_tasks, return_exceptions=True)
                        
                        # 更新任务状态
                        task_list = list(self.tasks.values())[-len(results):]
                        for task, result in zip(task_list, results):
                            if isinstance(result, Exception):
                                task.status = TaskStatus.FAILED
                                task.output = str(result)
                            else:
                                task.output = result
                                
                                # 审核
                                review = await self._review_output(goal, task, result)
                                if review.get("needs_revision") and task.attempts < task.max_attempts:
                                    task.status = TaskStatus.NEEDS_REVISION
                                    task.feedback = review.get("feedback", "")
                                else:
                                    task.status = TaskStatus.COMPLETED
                                    task.completed_at = time.time()
                else:
                    # 串行执行
                    for task_info in tasks_to_execute:
                        task = self._create_task(
                            description=task_info["description"],
                            input_data=task_info.get("input", {})
                        )
                        task.assigned_to = task_info["worker"]
                        
                        try:
                            result = await self._execute_task(task)
                            task.output = result
                            
                            # 审核
                            review = await self._review_output(goal, task, result)
                            if review.get("needs_revision") and task.attempts < task.max_attempts:
                                task.status = TaskStatus.NEEDS_REVISION
                                task.feedback = review.get("feedback", "")
                            else:
                                task.status = TaskStatus.COMPLETED
                                task.completed_at = time.time()
                                
                        except Exception as e:
                            task.status = TaskStatus.FAILED
                            task.output = str(e)
            
            elif action == "request_revision":
                # 处理需要修订的任务
                for task in self.tasks.values():
                    if task.status == TaskStatus.NEEDS_REVISION:
                        if task.attempts < task.max_attempts:
                            try:
                                result = await self._execute_task(task)
                                task.output = result
                                task.status = TaskStatus.COMPLETED
                                task.completed_at = time.time()
                            except Exception as e:
                                task.status = TaskStatus.FAILED
                                task.output = str(e)
                        else:
                            task.status = TaskStatus.FAILED
            
            # 检查是否需要人工审批
            if self.config.require_approval:
                # 这里可以添加人工审批逻辑
                pass
        
        # 达到最大迭代次数
        logger.warning(f"Supervisor reached max iterations ({self.config.max_iterations})")
        return {
            "status": "max_iterations_reached",
            "output": None,
            "iterations": self.iteration,
            "tasks": [t.to_dict() for t in self.tasks.values()]
        }
    
    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        return {
            "name": self.name,
            "iteration": self.iteration,
            "workers": {
                name: {
                    "description": w.description,
                    "available": w.available,
                    "current_tasks": w.current_tasks
                }
                for name, w in self.workers.items()
            },
            "tasks": {
                tid: t.to_dict()
                for tid, t in self.tasks.items()
            }
        }
    
    def __repr__(self) -> str:
        return f"Supervisor(name='{self.name}', workers={list(self.workers.keys())})"
