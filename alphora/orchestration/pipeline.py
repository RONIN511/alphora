"""
Pipeline 编排器 - 串行执行多个Agent

特性：
1. 按顺序执行多个Agent
2. 支持中间结果传递
3. 支持条件跳过
4. 支持错误处理和重试
5. 支持超时控制
"""

import asyncio
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union, Awaitable
from enum import Enum

logger = logging.getLogger(__name__)


class StepStatus(str, Enum):
    """步骤状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"


@dataclass
class StepResult:
    """步骤执行结果"""
    step_name: str
    status: StepStatus
    output: Any = None
    error: Optional[str] = None
    start_time: float = 0
    end_time: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration_ms(self) -> float:
        """执行耗时（毫秒）"""
        return (self.end_time - self.start_time) * 1000
    
    @property
    def success(self) -> bool:
        return self.status == StepStatus.SUCCESS


@dataclass
class PipelineStep:
    """
    Pipeline步骤定义
    
    示例：
    ```python
    step = PipelineStep(
        name="translate",
        handler=translator.translate,
        condition=lambda ctx: ctx.get("need_translate", True),
        transform_input=lambda ctx: {"text": ctx["content"]},
        transform_output=lambda out: {"translated": out}
    )
    ```
    """
    name: str
    handler: Callable[..., Awaitable[Any]]  # 异步处理函数
    condition: Optional[Callable[[Dict], bool]] = None  # 执行条件
    transform_input: Optional[Callable[[Dict], Dict]] = None  # 输入转换
    transform_output: Optional[Callable[[Any], Any]] = None  # 输出转换
    on_error: Optional[Callable[[Exception], Any]] = None  # 错误处理
    timeout: Optional[float] = None  # 超时时间（秒）
    retry_count: int = 0  # 重试次数
    retry_delay: float = 1.0  # 重试延迟（秒）
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineContext:
    """Pipeline执行上下文"""
    input_data: Dict[str, Any]
    current_step: int = 0
    results: List[StepResult] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)  # 累积数据
    start_time: float = field(default_factory=time.time)
    
    def update(self, key: str, value: Any):
        """更新上下文数据"""
        self.data[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取上下文数据"""
        return self.data.get(key, default)
    
    @property
    def last_output(self) -> Any:
        """获取上一步的输出"""
        if not self.results:
            return self.input_data
        return self.results[-1].output
    
    @property
    def all_outputs(self) -> Dict[str, Any]:
        """获取所有步骤的输出"""
        return {r.step_name: r.output for r in self.results if r.success}


class Pipeline:
    """
    Pipeline 编排器
    
    按顺序执行多个Agent，支持数据在步骤间传递。
    
    使用示例：
    ```python
    # 创建Pipeline
    pipeline = Pipeline(name="document_processor")
    
    # 添加步骤
    pipeline.add_step(PipelineStep(
        name="extract",
        handler=extractor.extract,
        transform_input=lambda ctx: {"document": ctx["file"]}
    ))
    
    pipeline.add_step(PipelineStep(
        name="summarize", 
        handler=summarizer.summarize,
        transform_input=lambda ctx: {"text": ctx.last_output}
    ))
    
    pipeline.add_step(PipelineStep(
        name="translate",
        handler=translator.translate,
        condition=lambda ctx: ctx.get("target_lang") != "zh",
        transform_input=lambda ctx: {"text": ctx.last_output}
    ))
    
    # 执行
    result = await pipeline.run({"file": document, "target_lang": "en"})
    ```
    """
    
    def __init__(
        self,
        name: str = "pipeline",
        steps: Optional[List[PipelineStep]] = None,
        on_step_start: Optional[Callable[[PipelineStep, PipelineContext], None]] = None,
        on_step_end: Optional[Callable[[PipelineStep, StepResult], None]] = None,
        on_error: Optional[Callable[[PipelineStep, Exception], None]] = None,
        stop_on_error: bool = True
    ):
        self.name = name
        self.steps: List[PipelineStep] = steps or []
        self.on_step_start = on_step_start
        self.on_step_end = on_step_end
        self.on_error = on_error
        self.stop_on_error = stop_on_error
    
    def add_step(self, step: PipelineStep) -> "Pipeline":
        """添加步骤"""
        self.steps.append(step)
        return self
    
    def add_steps(self, steps: List[PipelineStep]) -> "Pipeline":
        """批量添加步骤"""
        self.steps.extend(steps)
        return self
    
    def insert_step(self, index: int, step: PipelineStep) -> "Pipeline":
        """在指定位置插入步骤"""
        self.steps.insert(index, step)
        return self
    
    def remove_step(self, name: str) -> bool:
        """移除指定名称的步骤"""
        for i, step in enumerate(self.steps):
            if step.name == name:
                self.steps.pop(i)
                return True
        return False
    
    async def _execute_step(
        self,
        step: PipelineStep,
        context: PipelineContext
    ) -> StepResult:
        """执行单个步骤"""
        result = StepResult(
            step_name=step.name,
            status=StepStatus.PENDING,
            start_time=time.time()
        )
        
        # 检查条件
        if step.condition and not step.condition(context):
            result.status = StepStatus.SKIPPED
            result.end_time = time.time()
            logger.info(f"Step '{step.name}' skipped due to condition")
            return result
        
        result.status = StepStatus.RUNNING
        
        # 准备输入
        if step.transform_input:
            step_input = step.transform_input(context)
        else:
            step_input = {"input": context.last_output}
        
        # 执行（带重试）
        last_error = None
        for attempt in range(step.retry_count + 1):
            try:
                # 执行处理函数
                if step.timeout:
                    output = await asyncio.wait_for(
                        step.handler(**step_input),
                        timeout=step.timeout
                    )
                else:
                    output = await step.handler(**step_input)
                
                # 转换输出
                if step.transform_output:
                    output = step.transform_output(output)
                
                result.output = output
                result.status = StepStatus.SUCCESS
                result.end_time = time.time()
                
                # 更新上下文
                context.data[step.name] = output
                
                return result
                
            except asyncio.TimeoutError:
                last_error = TimeoutError(f"Step '{step.name}' timed out after {step.timeout}s")
                result.status = StepStatus.TIMEOUT
                
            except Exception as e:
                last_error = e
                
                if attempt < step.retry_count:
                    logger.warning(f"Step '{step.name}' failed (attempt {attempt + 1}), retrying...")
                    await asyncio.sleep(step.retry_delay)
        
        # 所有重试都失败
        result.status = StepStatus.FAILED
        result.error = str(last_error)
        result.end_time = time.time()
        
        # 调用错误处理
        if step.on_error:
            try:
                fallback = step.on_error(last_error)
                if fallback is not None:
                    result.output = fallback
                    result.status = StepStatus.SUCCESS
            except Exception:
                pass
        
        return result
    
    async def run(
        self,
        input_data: Dict[str, Any],
        start_step: int = 0,
        end_step: Optional[int] = None
    ) -> PipelineContext:
        """
        执行Pipeline
        
        Args:
            input_data: 输入数据
            start_step: 起始步骤索引
            end_step: 结束步骤索引（不包含）
        
        Returns:
            执行上下文，包含所有步骤的结果
        """
        context = PipelineContext(
            input_data=input_data,
            data=input_data.copy()
        )
        
        steps_to_run = self.steps[start_step:end_step]
        
        logger.info(f"Pipeline '{self.name}' started with {len(steps_to_run)} steps")
        
        for i, step in enumerate(steps_to_run):
            context.current_step = start_step + i
            
            # 步骤开始回调
            if self.on_step_start:
                self.on_step_start(step, context)
            
            # 执行步骤
            result = await self._execute_step(step, context)
            context.results.append(result)
            
            # 步骤结束回调
            if self.on_step_end:
                self.on_step_end(step, result)
            
            # 检查是否需要停止
            if not result.success and result.status != StepStatus.SKIPPED:
                if self.on_error:
                    self.on_error(step, Exception(result.error))
                
                if self.stop_on_error:
                    logger.error(f"Pipeline stopped at step '{step.name}': {result.error}")
                    break
        
        total_time = (time.time() - context.start_time) * 1000
        success_count = sum(1 for r in context.results if r.success)
        
        logger.info(
            f"Pipeline '{self.name}' completed: "
            f"{success_count}/{len(context.results)} steps succeeded, "
            f"total time: {total_time:.2f}ms"
        )
        
        return context
    
    def __rshift__(self, other: Union["Pipeline", PipelineStep]) -> "Pipeline":
        """
        使用 >> 操作符连接Pipeline或Step
        
        示例：
        ```python
        pipeline = step1 >> step2 >> step3
        combined = pipeline1 >> pipeline2
        ```
        """
        new_pipeline = Pipeline(
            name=f"{self.name}_combined",
            steps=self.steps.copy()
        )
        
        if isinstance(other, Pipeline):
            new_pipeline.steps.extend(other.steps)
        elif isinstance(other, PipelineStep):
            new_pipeline.steps.append(other)
        else:
            raise TypeError(f"Cannot combine Pipeline with {type(other)}")
        
        return new_pipeline
    
    def __repr__(self) -> str:
        step_names = [s.name for s in self.steps]
        return f"Pipeline(name='{self.name}', steps={step_names})"


# 便捷函数
def step(
    name: str,
    handler: Callable[..., Awaitable[Any]],
    **kwargs
) -> PipelineStep:
    """创建Pipeline步骤的便捷函数"""
    return PipelineStep(name=name, handler=handler, **kwargs)
