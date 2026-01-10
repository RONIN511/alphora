"""
Workflow 编排器 - 复杂工作流

特性：
1. DAG（有向无环图）工作流定义
2. 条件分支和循环
3. 并行执行依赖无关的节点
4. 状态持久化和恢复
5. 可视化工作流
"""

import asyncio
import json
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Awaitable
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)


class NodeStatus(str, Enum):
    """节点状态"""
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class EdgeType(str, Enum):
    """边类型"""
    NORMAL = "normal"           # 普通依赖
    CONDITIONAL = "conditional" # 条件依赖
    LOOP = "loop"              # 循环


@dataclass
class WorkflowNode:
    """
    工作流节点
    
    示例：
    ```python
    node = WorkflowNode(
        id="process",
        handler=process_agent.run,
        inputs={"data": "{{fetch.output}}"},  # 引用其他节点的输出
        condition=lambda ctx: ctx.get("should_process", True)
    )
    ```
    """
    id: str
    handler: Callable[..., Awaitable[Any]]
    inputs: Dict[str, Any] = field(default_factory=dict)
    condition: Optional[Callable[[Dict], bool]] = None
    timeout: Optional[float] = None
    retry_count: int = 0
    retry_delay: float = 1.0
    on_error: Optional[Callable[[Exception], Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 运行时状态
    status: NodeStatus = NodeStatus.PENDING
    output: Any = None
    error: Optional[str] = None
    start_time: float = 0
    end_time: float = 0
    attempts: int = 0


@dataclass
class WorkflowEdge:
    """
    工作流边（节点间的依赖关系）
    """
    source: str  # 源节点ID
    target: str  # 目标节点ID
    edge_type: EdgeType = EdgeType.NORMAL
    condition: Optional[Callable[[Dict], bool]] = None  # 条件边
    transform: Optional[Callable[[Any], Any]] = None  # 数据转换


@dataclass
class WorkflowContext:
    """工作流执行上下文"""
    workflow_id: str
    inputs: Dict[str, Any]
    outputs: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    current_iteration: int = 0
    max_iterations: int = 100
    
    def get(self, key: str, default: Any = None) -> Any:
        # 先查变量，再查输出，最后查输入
        if key in self.variables:
            return self.variables[key]
        if key in self.outputs:
            return self.outputs[key]
        return self.inputs.get(key, default)
    
    def set(self, key: str, value: Any):
        self.variables[key] = value
    
    def resolve_value(self, value: Any) -> Any:
        """解析值中的引用，如 {{node_id.output}}"""
        if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
            ref = value[2:-2].strip()
            parts = ref.split(".")
            
            if len(parts) == 1:
                return self.get(parts[0])
            elif len(parts) == 2:
                node_id, attr = parts
                if node_id in self.outputs:
                    output = self.outputs[node_id]
                    if isinstance(output, dict):
                        return output.get(attr)
                    return output
            return None
        
        elif isinstance(value, dict):
            return {k: self.resolve_value(v) for k, v in value.items()}
        
        elif isinstance(value, list):
            return [self.resolve_value(v) for v in value]
        
        return value


class Workflow:
    """
    Workflow 编排器
    
    定义和执行复杂的DAG工作流。
    
    使用示例：
    ```python
    # 创建工作流
    workflow = Workflow(name="data_pipeline")
    
    # 添加节点
    workflow.add_node(WorkflowNode(
        id="fetch",
        handler=fetcher.fetch
    ))
    
    workflow.add_node(WorkflowNode(
        id="process",
        handler=processor.process,
        inputs={"data": "{{fetch.output}}"}
    ))
    
    workflow.add_node(WorkflowNode(
        id="save",
        handler=saver.save,
        inputs={"data": "{{process.output}}"}
    ))
    
    # 添加边（依赖关系）
    workflow.add_edge("fetch", "process")
    workflow.add_edge("process", "save")
    
    # 或使用链式语法
    workflow.chain("fetch", "process", "save")
    
    # 执行
    result = await workflow.run({"url": "https://example.com"})
    ```
    """
    
    def __init__(
        self,
        name: str = "workflow",
        nodes: Optional[List[WorkflowNode]] = None,
        edges: Optional[List[WorkflowEdge]] = None,
        max_parallel: int = 10,
        fail_fast: bool = True
    ):
        self.name = name
        self.nodes: Dict[str, WorkflowNode] = {}
        self.edges: List[WorkflowEdge] = edges or []
        self.max_parallel = max_parallel
        self.fail_fast = fail_fast
        
        # 图结构
        self._dependencies: Dict[str, Set[str]] = defaultdict(set)  # 节点依赖
        self._dependents: Dict[str, Set[str]] = defaultdict(set)    # 被依赖
        
        if nodes:
            for node in nodes:
                self.add_node(node)
    
    def add_node(self, node: WorkflowNode) -> "Workflow":
        """添加节点"""
        if node.id in self.nodes:
            raise ValueError(f"Node '{node.id}' already exists")
        self.nodes[node.id] = node
        return self
    
    def add_edge(
        self,
        source: str,
        target: str,
        edge_type: EdgeType = EdgeType.NORMAL,
        condition: Optional[Callable[[Dict], bool]] = None,
        transform: Optional[Callable[[Any], Any]] = None
    ) -> "Workflow":
        """添加边"""
        edge = WorkflowEdge(
            source=source,
            target=target,
            edge_type=edge_type,
            condition=condition,
            transform=transform
        )
        self.edges.append(edge)
        
        # 更新依赖关系
        self._dependencies[target].add(source)
        self._dependents[source].add(target)
        
        return self
    
    def chain(self, *node_ids: str) -> "Workflow":
        """链式连接多个节点"""
        for i in range(len(node_ids) - 1):
            self.add_edge(node_ids[i], node_ids[i + 1])
        return self
    
    def parallel(self, source: str, *targets: str) -> "Workflow":
        """从一个节点并行连接到多个节点"""
        for target in targets:
            self.add_edge(source, target)
        return self
    
    def merge(self, *sources: str, target: str) -> "Workflow":
        """多个节点汇聚到一个节点"""
        for source in sources:
            self.add_edge(source, target)
        return self
    
    def _get_ready_nodes(self, context: WorkflowContext) -> List[str]:
        """获取可以执行的节点"""
        ready = []
        
        for node_id, node in self.nodes.items():
            if node.status != NodeStatus.PENDING:
                continue
            
            # 检查所有依赖是否满足
            deps = self._dependencies[node_id]
            deps_satisfied = all(
                self.nodes[dep].status in (NodeStatus.SUCCESS, NodeStatus.SKIPPED)
                for dep in deps
            )
            
            if deps_satisfied:
                # 检查条件边
                edge_conditions_met = True
                for edge in self.edges:
                    if edge.target == node_id and edge.condition:
                        if not edge.condition(context.outputs):
                            edge_conditions_met = False
                            break
                
                if edge_conditions_met:
                    ready.append(node_id)
        
        return ready
    
    async def _execute_node(
        self,
        node: WorkflowNode,
        context: WorkflowContext
    ) -> bool:
        """执行单个节点"""
        node.status = NodeStatus.RUNNING
        node.start_time = time.time()
        node.attempts += 1
        
        # 检查节点条件
        if node.condition and not node.condition(context.outputs):
            node.status = NodeStatus.SKIPPED
            node.end_time = time.time()
            logger.info(f"Node '{node.id}' skipped due to condition")
            return True
        
        # 解析输入
        resolved_inputs = context.resolve_value(node.inputs)
        
        for attempt in range(node.retry_count + 1):
            try:
                if node.timeout:
                    result = await asyncio.wait_for(
                        node.handler(**resolved_inputs),
                        timeout=node.timeout
                    )
                else:
                    result = await node.handler(**resolved_inputs)
                
                node.output = result
                node.status = NodeStatus.SUCCESS
                node.end_time = time.time()
                
                # 保存输出到上下文
                context.outputs[node.id] = result
                
                logger.info(
                    f"Node '{node.id}' completed in "
                    f"{(node.end_time - node.start_time) * 1000:.2f}ms"
                )
                return True
                
            except asyncio.TimeoutError:
                node.error = f"Timeout after {node.timeout}s"
                
            except Exception as e:
                node.error = str(e)
                
                if attempt < node.retry_count:
                    logger.warning(
                        f"Node '{node.id}' failed (attempt {attempt + 1}), retrying..."
                    )
                    await asyncio.sleep(node.retry_delay)
        
        # 所有重试都失败
        node.status = NodeStatus.FAILED
        node.end_time = time.time()
        
        # 调用错误处理
        if node.on_error:
            try:
                fallback = node.on_error(Exception(node.error))
                if fallback is not None:
                    node.output = fallback
                    node.status = NodeStatus.SUCCESS
                    context.outputs[node.id] = fallback
                    return True
            except Exception:
                pass
        
        logger.error(f"Node '{node.id}' failed: {node.error}")
        return False
    
    def _reset_nodes(self):
        """重置所有节点状态"""
        for node in self.nodes.values():
            node.status = NodeStatus.PENDING
            node.output = None
            node.error = None
            node.start_time = 0
            node.end_time = 0
            node.attempts = 0
    
    def _validate(self):
        """验证工作流"""
        # 检查是否有环
        visited = set()
        rec_stack = set()
        
        def has_cycle(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)
            
            for dep in self._dependents[node_id]:
                if dep not in visited:
                    if has_cycle(dep):
                        return True
                elif dep in rec_stack:
                    return True
            
            rec_stack.remove(node_id)
            return False
        
        for node_id in self.nodes:
            if node_id not in visited:
                if has_cycle(node_id):
                    raise ValueError(f"Workflow has a cycle involving node '{node_id}'")
        
        # 检查边的节点是否存在
        for edge in self.edges:
            if edge.source not in self.nodes:
                raise ValueError(f"Edge source '{edge.source}' not found")
            if edge.target not in self.nodes:
                raise ValueError(f"Edge target '{edge.target}' not found")
    
    async def run(
        self,
        inputs: Optional[Dict[str, Any]] = None,
        resume_from: Optional[str] = None
    ) -> WorkflowContext:
        """
        执行工作流
        
        Args:
            inputs: 输入数据
            resume_from: 从指定节点恢复执行
        
        Returns:
            执行上下文
        """
        self._validate()
        
        if not resume_from:
            self._reset_nodes()
        
        context = WorkflowContext(
            workflow_id=f"{self.name}_{int(time.time())}",
            inputs=inputs or {}
        )
        
        logger.info(f"Workflow '{self.name}' started")
        
        semaphore = asyncio.Semaphore(self.max_parallel)
        
        async def run_node(node_id: str):
            async with semaphore:
                return await self._execute_node(self.nodes[node_id], context)
        
        while True:
            context.current_iteration += 1
            
            if context.current_iteration > context.max_iterations:
                logger.error(f"Workflow exceeded max iterations ({context.max_iterations})")
                break
            
            # 获取可执行的节点
            ready_nodes = self._get_ready_nodes(context)
            
            if not ready_nodes:
                # 检查是否还有未完成的节点
                pending = [
                    n.id for n in self.nodes.values()
                    if n.status == NodeStatus.PENDING
                ]
                running = [
                    n.id for n in self.nodes.values()
                    if n.status == NodeStatus.RUNNING
                ]
                
                if not pending and not running:
                    break  # 所有节点都完成了
                
                if not running:
                    # 有未完成的节点但无法执行（可能是依赖失败）
                    logger.warning(f"Workflow stuck with pending nodes: {pending}")
                    break
                
                await asyncio.sleep(0.1)
                continue
            
            # 并行执行就绪的节点
            tasks = [run_node(node_id) for node_id in ready_nodes]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 检查是否需要停止
            if self.fail_fast:
                for result in results:
                    if result is False or isinstance(result, Exception):
                        logger.error("Workflow stopped due to node failure (fail_fast=True)")
                        return context
        
        # 统计结果
        success_count = sum(1 for n in self.nodes.values() if n.status == NodeStatus.SUCCESS)
        failed_count = sum(1 for n in self.nodes.values() if n.status == NodeStatus.FAILED)
        skipped_count = sum(1 for n in self.nodes.values() if n.status == NodeStatus.SKIPPED)
        
        total_time = (time.time() - context.start_time) * 1000
        
        logger.info(
            f"Workflow '{self.name}' completed: "
            f"success={success_count}, failed={failed_count}, skipped={skipped_count}, "
            f"total_time={total_time:.2f}ms"
        )
        
        return context
    
    def get_status(self) -> Dict[str, Any]:
        """获取工作流状态"""
        return {
            "name": self.name,
            "nodes": {
                node_id: {
                    "status": node.status.value,
                    "output": node.output,
                    "error": node.error,
                    "duration_ms": (node.end_time - node.start_time) * 1000 if node.end_time else 0,
                    "attempts": node.attempts
                }
                for node_id, node in self.nodes.items()
            },
            "edges": [
                {"source": e.source, "target": e.target, "type": e.edge_type.value}
                for e in self.edges
            ]
        }
    
    def to_mermaid(self) -> str:
        """生成Mermaid图表"""
        lines = ["graph TD"]
        
        for node_id, node in self.nodes.items():
            label = node.id
            if node.status == NodeStatus.SUCCESS:
                lines.append(f"    {node_id}[{label}]:::success")
            elif node.status == NodeStatus.FAILED:
                lines.append(f"    {node_id}[{label}]:::failed")
            elif node.status == NodeStatus.RUNNING:
                lines.append(f"    {node_id}[{label}]:::running")
            else:
                lines.append(f"    {node_id}[{label}]")
        
        for edge in self.edges:
            if edge.edge_type == EdgeType.CONDITIONAL:
                lines.append(f"    {edge.source} -.-> {edge.target}")
            else:
                lines.append(f"    {edge.source} --> {edge.target}")
        
        lines.append("    classDef success fill:#90EE90")
        lines.append("    classDef failed fill:#FFB6C1")
        lines.append("    classDef running fill:#87CEEB")
        
        return "\n".join(lines)
    
    def __repr__(self) -> str:
        return f"Workflow(name='{self.name}', nodes={list(self.nodes.keys())})"


# 便捷装饰器
def node(
    workflow: Workflow,
    node_id: str,
    **kwargs
):
    """
    节点装饰器
    
    示例：
    ```python
    workflow = Workflow()
    
    @node(workflow, "fetch")
    async def fetch_data(url: str):
        return await http_client.get(url)
    
    @node(workflow, "process", inputs={"data": "{{fetch.output}}"})
    async def process_data(data):
        return data.upper()
    ```
    """
    def decorator(func: Callable[..., Awaitable[Any]]):
        workflow_node = WorkflowNode(
            id=node_id,
            handler=func,
            **kwargs
        )
        workflow.add_node(workflow_node)
        return func
    return decorator
