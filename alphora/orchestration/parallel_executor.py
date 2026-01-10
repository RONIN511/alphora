"""
ParallelExecutor 编排器 - 并行执行

特性：
1. 并行执行多个Agent
2. 支持结果聚合策略
3. 支持超时和错误处理
4. 支持部分成功
"""

import asyncio
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union, Awaitable
from enum import Enum

logger = logging.getLogger(__name__)


class AggregationStrategy(str, Enum):
    """结果聚合策略"""
    ALL = "all"              # 返回所有结果
    FIRST = "first"          # 返回第一个成功的结果
    MAJORITY = "majority"    # 返回多数一致的结果
    MERGE = "merge"          # 合并所有结果
    CUSTOM = "custom"        # 自定义聚合


@dataclass
class ExecutorTask:
    """执行器任务"""
    name: str
    handler: Callable[..., Awaitable[Any]]
    args: tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    timeout: Optional[float] = None
    weight: float = 1.0  # 权重（用于MAJORITY策略）
    required: bool = True  # 是否必须成功


@dataclass
class TaskResult:
    """任务执行结果"""
    name: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0


@dataclass
class ParallelResult:
    """并行执行结果"""
    success: bool
    results: List[TaskResult]
    aggregated_output: Any = None
    total_duration_ms: float = 0
    
    @property
    def successful_results(self) -> List[TaskResult]:
        return [r for r in self.results if r.success]
    
    @property
    def failed_results(self) -> List[TaskResult]:
        return [r for r in self.results if not r.success]
    
    @property
    def success_rate(self) -> float:
        if not self.results:
            return 0.0
        return len(self.successful_results) / len(self.results)


class ParallelExecutor:
    """
    ParallelExecutor 编排器
    
    并行执行多个Agent，支持多种结果聚合策略。
    
    使用示例：
    ```python
    # 创建并行执行器
    executor = ParallelExecutor(
        name="multi_search",
        strategy=AggregationStrategy.MERGE,
        timeout=30.0
    )
    
    # 添加任务
    executor.add_task(ExecutorTask(
        name="google",
        handler=google_search,
        kwargs={"query": "AI"}
    ))
    
    executor.add_task(ExecutorTask(
        name="bing",
        handler=bing_search,
        kwargs={"query": "AI"}
    ))
    
    # 执行
    result = await executor.run()
    print(result.aggregated_output)
    ```
    """
    
    def __init__(
        self,
        name: str = "parallel_executor",
        tasks: Optional[List[ExecutorTask]] = None,
        strategy: AggregationStrategy = AggregationStrategy.ALL,
        aggregator: Optional[Callable[[List[TaskResult]], Any]] = None,
        timeout: Optional[float] = None,
        fail_fast: bool = False,  # 遇到错误立即停止
        min_success_rate: float = 0.0  # 最小成功率要求
    ):
        self.name = name
        self.tasks: List[ExecutorTask] = tasks or []
        self.strategy = strategy
        self.aggregator = aggregator
        self.timeout = timeout
        self.fail_fast = fail_fast
        self.min_success_rate = min_success_rate
    
    def add_task(self, task: ExecutorTask) -> "ParallelExecutor":
        """添加任务"""
        self.tasks.append(task)
        return self
    
    def add_tasks(self, tasks: List[ExecutorTask]) -> "ParallelExecutor":
        """批量添加任务"""
        self.tasks.extend(tasks)
        return self
    
    def add_handler(
        self,
        name: str,
        handler: Callable[..., Awaitable[Any]],
        *args,
        timeout: Optional[float] = None,
        weight: float = 1.0,
        required: bool = True,
        **kwargs
    ) -> "ParallelExecutor":
        """添加处理函数"""
        task = ExecutorTask(
            name=name,
            handler=handler,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            weight=weight,
            required=required
        )
        self.tasks.append(task)
        return self
    
    async def _execute_task(self, task: ExecutorTask) -> TaskResult:
        """执行单个任务"""
        start_time = time.time()
        
        try:
            # 确定超时时间
            timeout = task.timeout or self.timeout
            
            if timeout:
                output = await asyncio.wait_for(
                    task.handler(*task.args, **task.kwargs),
                    timeout=timeout
                )
            else:
                output = await task.handler(*task.args, **task.kwargs)
            
            duration = (time.time() - start_time) * 1000
            
            return TaskResult(
                name=task.name,
                success=True,
                output=output,
                duration_ms=duration
            )
            
        except asyncio.TimeoutError:
            duration = (time.time() - start_time) * 1000
            return TaskResult(
                name=task.name,
                success=False,
                error=f"Timeout after {task.timeout or self.timeout}s",
                duration_ms=duration
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return TaskResult(
                name=task.name,
                success=False,
                error=str(e),
                duration_ms=duration
            )
    
    def _aggregate_results(self, results: List[TaskResult]) -> Any:
        """聚合结果"""
        successful = [r for r in results if r.success]
        
        if self.strategy == AggregationStrategy.ALL:
            # 返回所有结果
            return {r.name: r.output for r in results}
        
        elif self.strategy == AggregationStrategy.FIRST:
            # 返回第一个成功的结果
            for r in results:
                if r.success:
                    return r.output
            return None
        
        elif self.strategy == AggregationStrategy.MAJORITY:
            # 返回多数一致的结果（简化版：返回出现次数最多的结果）
            if not successful:
                return None
            
            # 统计结果出现次数（加权）
            result_counts: Dict[str, float] = {}
            result_map: Dict[str, Any] = {}
            
            for r in successful:
                # 找到对应的任务获取权重
                weight = 1.0
                for task in self.tasks:
                    if task.name == r.name:
                        weight = task.weight
                        break
                
                output_key = str(r.output)
                result_counts[output_key] = result_counts.get(output_key, 0) + weight
                result_map[output_key] = r.output
            
            # 返回权重最高的结果
            if result_counts:
                max_key = max(result_counts, key=result_counts.get)
                return result_map[max_key]
            return None
        
        elif self.strategy == AggregationStrategy.MERGE:
            # 合并所有结果
            merged = {}
            for r in successful:
                if isinstance(r.output, dict):
                    merged.update(r.output)
                else:
                    merged[r.name] = r.output
            return merged
        
        elif self.strategy == AggregationStrategy.CUSTOM:
            # 使用自定义聚合器
            if self.aggregator:
                return self.aggregator(results)
            return None
        
        return None
    
    async def run(self, **kwargs) -> ParallelResult:
        """
        执行所有任务
        
        Args:
            **kwargs: 传递给所有任务的额外参数
        
        Returns:
            并行执行结果
        """
        if not self.tasks:
            return ParallelResult(
                success=True,
                results=[],
                total_duration_ms=0
            )
        
        start_time = time.time()
        
        # 更新任务的kwargs
        for task in self.tasks:
            task.kwargs.update(kwargs)
        
        # 创建所有任务
        coroutines = [self._execute_task(task) for task in self.tasks]
        
        if self.fail_fast:
            # 使用 as_completed 实现 fail_fast
            results = []
            for coro in asyncio.as_completed(coroutines):
                result = await coro
                results.append(result)
                
                # 检查必须成功的任务是否失败
                if not result.success:
                    for task in self.tasks:
                        if task.name == result.name and task.required:
                            # 取消剩余任务
                            for remaining in coroutines:
                                if hasattr(remaining, 'cancel'):
                                    remaining.cancel()
                            break
        else:
            # 并行执行所有任务
            results = await asyncio.gather(*coroutines, return_exceptions=False)
        
        total_duration = (time.time() - start_time) * 1000
        
        # 计算成功率
        success_count = sum(1 for r in results if r.success)
        success_rate = success_count / len(results) if results else 0
        
        # 检查必须成功的任务
        required_failed = False
        for result in results:
            if not result.success:
                for task in self.tasks:
                    if task.name == result.name and task.required:
                        required_failed = True
                        break
        
        # 判断整体是否成功
        overall_success = (
            not required_failed and
            success_rate >= self.min_success_rate
        )
        
        # 聚合结果
        aggregated = self._aggregate_results(results) if overall_success else None
        
        return ParallelResult(
            success=overall_success,
            results=results,
            aggregated_output=aggregated,
            total_duration_ms=total_duration
        )
    
    async def map(
        self,
        items: List[Any],
        handler: Callable[..., Awaitable[Any]],
        concurrency: int = 10
    ) -> List[TaskResult]:
        """
        并行映射处理
        
        Args:
            items: 待处理的项目列表
            handler: 处理函数
            concurrency: 最大并发数
        
        Returns:
            处理结果列表
        """
        semaphore = asyncio.Semaphore(concurrency)
        
        async def limited_handler(item, index):
            async with semaphore:
                start_time = time.time()
                try:
                    output = await handler(item)
                    return TaskResult(
                        name=f"item_{index}",
                        success=True,
                        output=output,
                        duration_ms=(time.time() - start_time) * 1000
                    )
                except Exception as e:
                    return TaskResult(
                        name=f"item_{index}",
                        success=False,
                        error=str(e),
                        duration_ms=(time.time() - start_time) * 1000
                    )
        
        tasks = [limited_handler(item, i) for i, item in enumerate(items)]
        return await asyncio.gather(*tasks)
    
    def __or__(self, other: Union["ParallelExecutor", ExecutorTask]) -> "ParallelExecutor":
        """使用 | 操作符合并执行器或添加任务"""
        new_executor = ParallelExecutor(
            name=f"{self.name}_combined",
            tasks=self.tasks.copy(),
            strategy=self.strategy,
            aggregator=self.aggregator,
            timeout=self.timeout
        )
        
        if isinstance(other, ParallelExecutor):
            new_executor.tasks.extend(other.tasks)
        elif isinstance(other, ExecutorTask):
            new_executor.tasks.append(other)
        
        return new_executor
    
    def __repr__(self) -> str:
        task_names = [t.name for t in self.tasks]
        return f"ParallelExecutor(name='{self.name}', tasks={task_names})"


# 便捷函数
def parallel(*handlers: Callable[..., Awaitable[Any]], **kwargs) -> ParallelExecutor:
    """
    创建并行执行器的便捷函数
    
    示例：
    ```python
    result = await parallel(
        search_google,
        search_bing,
        search_duckduckgo,
        strategy=AggregationStrategy.MERGE
    ).run(query="AI")
    ```
    """
    executor = ParallelExecutor(**kwargs)
    for i, handler in enumerate(handlers):
        executor.add_task(ExecutorTask(
            name=handler.__name__ if hasattr(handler, '__name__') else f"task_{i}",
            handler=handler
        ))
    return executor
