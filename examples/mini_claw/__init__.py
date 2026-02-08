"""
Alphora Evo - Self-Evolving AI Agent System

基于 Alphora 框架的自进化智能体系统，通过执行者-审查者架构
实现任务的高质量自主完成。

Architecture:
    ┌─────────────┐
    │   Planner   │  任务分解与规划
    └──────┬──────┘
           │
    ┌──────▼──────┐     ┌─────────────┐
    │  Executor   │◄───►│  Reviewer    │  执行-审查循环
    └──────┬──────┘     └─────────────┘
           │
    ┌──────▼──────┐
    │ MemoryGuard │  智能记忆管理
    └─────────────┘
"""

from .engine import EvolutionEngine, EvolutionReport, TaskResult
from .executor import ExecutorAgent
from .reviewer import ReviewerAgent
from .planner import PlannerAgent
from .memory_guard import MemoryGuard

__version__ = "0.1.0"
__all__ = [
    "EvolutionEngine",
    "EvolutionReport",
    "TaskResult",
    "ExecutorAgent",
    "ReviewerAgent",
    "PlannerAgent",
    "MemoryGuard",
]
