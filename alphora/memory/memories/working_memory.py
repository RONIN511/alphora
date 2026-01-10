"""
工作记忆 - Agent执行过程中的临时状态管理

特性：
1. 存储当前任务的中间状态
2. 支持栈结构（用于递归任务）
3. 支持槽位系统（用于结构化信息）
4. 自动过期清理
5. 上下文切换
"""

import time
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, TypeVar
from collections import deque
from contextlib import contextmanager, asynccontextmanager
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class WorkingMemorySlot:
    """工作记忆槽位"""
    name: str
    value: Any
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at
    
    def update(self, value: Any):
        self.value = value
        self.updated_at = time.time()


@dataclass
class TaskFrame:
    """任务栈帧"""
    task_id: str
    task_name: str
    state: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    parent_id: Optional[str] = None


class WorkingMemory:
    """
    工作记忆
    
    用于Agent执行过程中的临时状态管理，类似于人类的工作记忆。
    
    使用示例：
    ```python
    # 创建工作记忆
    wm = WorkingMemory(capacity=10)
    
    # 设置槽位
    wm.set_slot("current_task", "分析用户问题")
    wm.set_slot("user_intent", "查询天气", ttl=300)
    
    # 获取槽位
    task = wm.get_slot("current_task")
    
    # 使用任务栈
    wm.push_task("main_task", state={"query": "天气如何"})
    wm.push_task("sub_task", state={"action": "获取位置"})
    
    # 处理完子任务后弹出
    frame = wm.pop_task()
    
    # 上下文管理
    async with wm.task_context("analyze", state={"step": 1}):
        # 执行任务
        wm.update_task_state(step=2)
    ```
    """
    
    def __init__(
        self,
        capacity: int = 7,  # 工作记忆容量（模拟人类的7±2限制）
        default_ttl: Optional[int] = None,
        auto_cleanup_interval: int = 60
    ):
        self.capacity = capacity
        self.default_ttl = default_ttl
        self.auto_cleanup_interval = auto_cleanup_interval
        
        # 槽位存储
        self._slots: Dict[str, WorkingMemorySlot] = {}
        
        # 任务栈
        self._task_stack: deque[TaskFrame] = deque()
        self._task_counter = 0
        
        # 注意力焦点
        self._focus: Optional[str] = None
        
        # 最近访问的槽位（用于LRU）
        self._access_order: deque[str] = deque()
        
        # 清理任务
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """启动自动清理任务"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._auto_cleanup())
    
    async def stop(self):
        """停止自动清理任务"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
    
    async def _auto_cleanup(self):
        """自动清理过期槽位"""
        while True:
            try:
                await asyncio.sleep(self.auto_cleanup_interval)
                self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Working memory cleanup error: {e}")
    
    def _cleanup_expired(self):
        """清理过期的槽位"""
        expired = [
            name for name, slot in self._slots.items()
            if slot.is_expired
        ]
        for name in expired:
            del self._slots[name]
            if name in self._access_order:
                self._access_order.remove(name)
    
    def _evict_if_needed(self):
        """如果超出容量则淘汰"""
        while len(self._slots) >= self.capacity:
            # 淘汰最久未访问的（但不能是焦点）
            while self._access_order:
                oldest = self._access_order.popleft()
                if oldest in self._slots and oldest != self._focus:
                    del self._slots[oldest]
                    break
    
    def _update_access(self, name: str):
        """更新访问顺序"""
        if name in self._access_order:
            self._access_order.remove(name)
        self._access_order.append(name)
    
    # ==================== 槽位操作 ====================
    
    def set_slot(
        self,
        name: str,
        value: Any,
        ttl: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """设置槽位值"""
        self._cleanup_expired()
        
        if name in self._slots:
            # 更新现有槽位
            slot = self._slots[name]
            slot.update(value)
            if ttl is not None:
                slot.expires_at = time.time() + ttl
            if metadata:
                slot.metadata.update(metadata)
        else:
            # 创建新槽位
            self._evict_if_needed()
            
            expires_at = None
            if ttl is not None:
                expires_at = time.time() + ttl
            elif self.default_ttl is not None:
                expires_at = time.time() + self.default_ttl
            
            self._slots[name] = WorkingMemorySlot(
                name=name,
                value=value,
                expires_at=expires_at,
                metadata=metadata or {}
            )
        
        self._update_access(name)
    
    def get_slot(self, name: str, default: Any = None) -> Any:
        """获取槽位值"""
        self._cleanup_expired()
        
        slot = self._slots.get(name)
        if slot is None:
            return default
        
        if slot.is_expired:
            del self._slots[name]
            return default
        
        self._update_access(name)
        return slot.value
    
    def has_slot(self, name: str) -> bool:
        """检查槽位是否存在"""
        slot = self._slots.get(name)
        return slot is not None and not slot.is_expired
    
    def remove_slot(self, name: str) -> bool:
        """移除槽位"""
        if name in self._slots:
            del self._slots[name]
            if name in self._access_order:
                self._access_order.remove(name)
            return True
        return False
    
    def get_all_slots(self) -> Dict[str, Any]:
        """获取所有有效槽位"""
        self._cleanup_expired()
        return {name: slot.value for name, slot in self._slots.items()}
    
    def clear_slots(self):
        """清空所有槽位"""
        self._slots.clear()
        self._access_order.clear()
    
    # ==================== 注意力焦点 ====================
    
    def set_focus(self, name: str):
        """设置注意力焦点"""
        if name in self._slots:
            self._focus = name
            self._update_access(name)
    
    def get_focus(self) -> Optional[Any]:
        """获取当前焦点的值"""
        if self._focus and self._focus in self._slots:
            return self._slots[self._focus].value
        return None
    
    def clear_focus(self):
        """清除焦点"""
        self._focus = None
    
    # ==================== 任务栈操作 ====================
    
    def push_task(
        self,
        task_name: str,
        state: Optional[Dict[str, Any]] = None
    ) -> str:
        """压入新任务"""
        self._task_counter += 1
        task_id = f"task_{self._task_counter}"
        
        parent_id = None
        if self._task_stack:
            parent_id = self._task_stack[-1].task_id
        
        frame = TaskFrame(
            task_id=task_id,
            task_name=task_name,
            state=state or {},
            parent_id=parent_id
        )
        
        self._task_stack.append(frame)
        return task_id
    
    def pop_task(self) -> Optional[TaskFrame]:
        """弹出当前任务"""
        if self._task_stack:
            return self._task_stack.pop()
        return None
    
    def peek_task(self) -> Optional[TaskFrame]:
        """查看当前任务（不弹出）"""
        if self._task_stack:
            return self._task_stack[-1]
        return None
    
    def get_task_state(self, key: str, default: Any = None) -> Any:
        """获取当前任务状态"""
        frame = self.peek_task()
        if frame:
            return frame.state.get(key, default)
        return default
    
    def update_task_state(self, **kwargs):
        """更新当前任务状态"""
        frame = self.peek_task()
        if frame:
            frame.state.update(kwargs)
    
    def get_task_depth(self) -> int:
        """获取任务栈深度"""
        return len(self._task_stack)
    
    def get_task_chain(self) -> List[str]:
        """获取任务链（从根到当前）"""
        return [frame.task_name for frame in self._task_stack]
    
    # ==================== 上下文管理 ====================
    
    @contextmanager
    def slot_context(self, name: str, value: Any, **kwargs):
        """
        槽位上下文管理器
        
        退出时自动清理槽位
        """
        self.set_slot(name, value, **kwargs)
        try:
            yield self.get_slot(name)
        finally:
            self.remove_slot(name)
    
    @contextmanager
    def task_context(self, task_name: str, state: Optional[Dict[str, Any]] = None):
        """
        任务上下文管理器
        
        退出时自动弹出任务
        """
        task_id = self.push_task(task_name, state)
        try:
            yield task_id
        finally:
            self.pop_task()
    
    @asynccontextmanager
    async def async_task_context(self, task_name: str, state: Optional[Dict[str, Any]] = None):
        """异步任务上下文管理器"""
        task_id = self.push_task(task_name, state)
        try:
            yield task_id
        finally:
            self.pop_task()
    
    # ==================== 批量操作 ====================
    
    def bulk_set(self, items: Dict[str, Any], ttl: Optional[int] = None):
        """批量设置槽位"""
        for name, value in items.items():
            self.set_slot(name, value, ttl=ttl)
    
    def bulk_get(self, names: List[str]) -> Dict[str, Any]:
        """批量获取槽位"""
        return {name: self.get_slot(name) for name in names if self.has_slot(name)}
    
    # ==================== 状态导出 ====================
    
    def snapshot(self) -> Dict[str, Any]:
        """创建当前状态快照"""
        self._cleanup_expired()
        
        return {
            "slots": {
                name: {
                    "value": slot.value,
                    "metadata": slot.metadata,
                    "created_at": slot.created_at,
                    "updated_at": slot.updated_at,
                    "expires_at": slot.expires_at
                }
                for name, slot in self._slots.items()
            },
            "task_stack": [
                {
                    "task_id": frame.task_id,
                    "task_name": frame.task_name,
                    "state": frame.state,
                    "created_at": frame.created_at,
                    "parent_id": frame.parent_id
                }
                for frame in self._task_stack
            ],
            "focus": self._focus,
            "capacity": self.capacity
        }
    
    def restore(self, snapshot: Dict[str, Any]):
        """从快照恢复状态"""
        self.clear_slots()
        self._task_stack.clear()
        
        # 恢复槽位
        for name, data in snapshot.get("slots", {}).items():
            slot = WorkingMemorySlot(
                name=name,
                value=data["value"],
                created_at=data.get("created_at", time.time()),
                updated_at=data.get("updated_at", time.time()),
                expires_at=data.get("expires_at"),
                metadata=data.get("metadata", {})
            )
            self._slots[name] = slot
        
        # 恢复任务栈
        for data in snapshot.get("task_stack", []):
            frame = TaskFrame(
                task_id=data["task_id"],
                task_name=data["task_name"],
                state=data.get("state", {}),
                created_at=data.get("created_at", time.time()),
                parent_id=data.get("parent_id")
            )
            self._task_stack.append(frame)
        
        # 恢复焦点
        self._focus = snapshot.get("focus")
    
    def stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "slot_count": len(self._slots),
            "capacity": self.capacity,
            "utilization": len(self._slots) / self.capacity if self.capacity > 0 else 0,
            "task_depth": len(self._task_stack),
            "focus": self._focus,
            "slot_names": list(self._slots.keys()),
            "task_chain": self.get_task_chain()
        }
    
    def __repr__(self) -> str:
        return (
            f"WorkingMemory(slots={len(self._slots)}/{self.capacity}, "
            f"task_depth={len(self._task_stack)}, focus={self._focus})"
        )
