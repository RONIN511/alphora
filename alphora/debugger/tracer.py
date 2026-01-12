"""
Alphora Debugger

用法：
    agent = BaseAgent(llm=llm, debugger=True)  # 自动启动调试面板
"""

import os
import time
import threading
import json
from uuid import uuid4
from enum import Enum
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict


class EventType(str, Enum):
    AGENT_CREATED = "agent_created"
    AGENT_DERIVED = "agent_derived"
    LLM_CALL_START = "llm_call_start"
    LLM_CALL_END = "llm_call_end"
    LLM_CALL_ERROR = "llm_call_error"
    PROMPT_CREATED = "prompt_created"
    MEMORY_ADD = "memory_add"
    MEMORY_RETRIEVE = "memory_retrieve"
    MEMORY_CLEAR = "memory_clear"
    TOOL_CALL = "tool_call"
    CUSTOM = "custom"


@dataclass
class DebugEvent:
    event_id: str
    event_type: EventType
    timestamp: float
    agent_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "agent_id": self.agent_id,
            "data": self.data
        }


@dataclass
class AgentInfo:
    agent_id: str
    agent_type: str
    created_at: float
    parent_id: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)
    llm_info: Dict[str, Any] = field(default_factory=dict)
    children_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LLMCallInfo:
    call_id: str
    agent_id: str
    model_name: str
    start_time: float
    input_messages: List[Dict] = field(default_factory=list)
    input_text: str = ""
    output_text: str = ""
    reasoning_text: str = ""
    end_time: Optional[float] = None
    token_usage: Dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def duration_ms(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d['duration_ms'] = self.duration_ms
        return d


class DebugTracer:
    """调试追踪器（单例）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._enabled = False
        self._server_started = False
        self._server_port = 9527

        # 数据存储
        self._events: List[DebugEvent] = []
        self._agents: Dict[str, AgentInfo] = {}
        self._llm_calls: Dict[str, LLMCallInfo] = {}
        self._call_graph: Dict[str, List[str]] = {}

        self._stats = {
            'total_events': 0,
            'total_llm_calls': 0,
            'total_tokens': 0,
            'total_duration_ms': 0.0,
            'errors': 0
        }

        self._max_events = 10000
        self._data_lock = threading.RLock()
        self._event_seq = 0

    # ==================== 控制 ====================

    def enable(self, start_server: bool = True, port: int = 9527):
        """启用调试"""
        if self._enabled and self._server_started:
            return  # 已启用

        self._enabled = True
        self._server_port = port

        if start_server and not self._server_started:
            self._start_server(port)

    def disable(self):
        """禁用调试（服务器保持运行以便查看历史数据）"""
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def server_url(self) -> str:
        return f"http://localhost:{self._server_port}/"

    def _start_server(self, port: int):
        """启动调试服务器"""
        try:
            from .server import start_server_background
            start_server_background(port)
            self._server_started = True
        except ImportError:
            import logging
            logging.warning(f"[Debugger] 需要安装: pip install fastapi uvicorn")
        except Exception as e:
            import logging
            logging.warning(f"[Debugger] 启动失败: {e}")

    def clear(self):
        """清空数据"""
        with self._data_lock:
            self._events.clear()
            self._agents.clear()
            self._llm_calls.clear()
            self._call_graph.clear()
            self._stats = {'total_events': 0, 'total_llm_calls': 0, 'total_tokens': 0, 'total_duration_ms': 0.0, 'errors': 0}
            self._event_seq = 0

    def _add_event(self, event: DebugEvent):
        if not self._enabled:
            return
        with self._data_lock:
            self._event_seq += 1
            self._events.append(event)
            self._stats['total_events'] += 1
            if len(self._events) > self._max_events:
                self._events = self._events[-self._max_events:]

    # ==================== Agent ====================

    def track_agent_created(self, agent, parent_id: Optional[str] = None):
        if not self._enabled:
            return

        agent_id = getattr(agent, 'agent_id', str(uuid4()))
        # agent_type = getattr(agent, 'agent_type', agent.__class__.__name__)
        agent_type = agent.__class__.__name__

        llm_info = {}
        llm = getattr(agent, 'llm', None)
        if llm:
            llm_info = {'model_name': getattr(llm, 'model_name', 'unknown'), 'base_url': getattr(llm, 'base_url', '')}

        info = AgentInfo(agent_id=agent_id, agent_type=agent_type, created_at=time.time(),
                         parent_id=parent_id, config=dict(getattr(agent, 'config', {})), llm_info=llm_info)

        with self._data_lock:
            self._agents[agent_id] = info
            if parent_id and parent_id in self._agents:
                self._agents[parent_id].children_ids.append(agent_id)

        self._add_event(DebugEvent(str(uuid4()), EventType.AGENT_CREATED, time.time(), agent_id,
                                   {'agent_type': agent_type, 'parent_id': parent_id, 'llm_info': llm_info}))

    def track_agent_derived(self, parent_agent, child_agent):
        if not self._enabled:
            return
        self._add_event(DebugEvent(str(uuid4()), EventType.AGENT_DERIVED, time.time(),
                                   getattr(parent_agent, 'agent_id', 'unknown'),
                                   {'child_id': getattr(child_agent, 'agent_id', ''),
                                    'child_type': getattr(child_agent, 'agent_type', '')}))

    # ==================== LLM ====================

    def track_llm_start(self,
                        agent_id: str,
                        model_name: str,
                        messages: Optional[List[Dict]] = None,
                        input_text: str = "") -> str:

        call_id = str(uuid4())

        if not self._enabled:
            return call_id

        with self._data_lock:
            self._llm_calls[call_id] = LLMCallInfo(
                call_id=call_id, agent_id=agent_id, model_name=model_name,
                start_time=time.time(), input_messages=messages or [], input_text=input_text[:2000]
            )
            self._stats['total_llm_calls'] += 1

        preview = input_text[:500] if input_text else (messages[-1].get('content', '')[:500] if messages else '')
        self._add_event(DebugEvent(str(uuid4()), EventType.LLM_CALL_START, time.time(), agent_id,
                                   {'call_id': call_id, 'model_name': model_name, 'input_preview': preview}))
        return call_id

    def track_llm_end(self, call_id: str, output_text: str = "",
                      reasoning_text: str = "", token_usage: Optional[Dict[str, int]] = None):
        if not self._enabled or call_id not in self._llm_calls:
            return

        with self._data_lock:
            call = self._llm_calls[call_id]
            call.end_time = time.time()
            call.output_text = output_text[:5000]
            call.reasoning_text = reasoning_text[:2000]
            call.token_usage = token_usage or {}
            if token_usage:
                self._stats['total_tokens'] += token_usage.get('total_tokens', 0)
            self._stats['total_duration_ms'] += call.duration_ms
            agent_id, duration = call.agent_id, call.duration_ms

        self._add_event(DebugEvent(str(uuid4()), EventType.LLM_CALL_END, time.time(), agent_id,
                                   {'call_id': call_id, 'duration_ms': duration, 'token_usage': token_usage,
                                    'output_preview': output_text[:500]}))

    def track_llm_error(self, call_id: str, error: str):
        if not self._enabled:
            return
        agent_id = 'unknown'
        with self._data_lock:
            if call_id in self._llm_calls:
                self._llm_calls[call_id].error = error
                self._llm_calls[call_id].end_time = time.time()
                agent_id = self._llm_calls[call_id].agent_id
            self._stats['errors'] += 1
        self._add_event(DebugEvent(str(uuid4()), EventType.LLM_CALL_ERROR, time.time(), agent_id,
                                   {'call_id': call_id, 'error': error[:1000]}))

    # ==================== Prompt ====================

    def track_prompt_created(self, agent_id: str, system_prompt: Optional[str] = None,
                             enable_memory: bool = False, memory_id: Optional[str] = None):
        if not self._enabled:
            return
        self._add_event(DebugEvent(str(uuid4()), EventType.PROMPT_CREATED, time.time(), agent_id,
                                   {'system_prompt_preview': system_prompt[:200] if system_prompt else None,
                                    'enable_memory': enable_memory, 'memory_id': memory_id}))

    # ==================== Memory ====================

    def track_memory_add(self, memory_id: str, role: str, content: str, agent_id: Optional[str] = None):
        if not self._enabled:
            return
        self._add_event(DebugEvent(str(uuid4()), EventType.MEMORY_ADD, time.time(), agent_id,
                                   {'memory_id': memory_id, 'role': role, 'content_preview': content[:200]}))

    def track_memory_retrieve(self, memory_id: str, rounds: int, message_count: int, agent_id: Optional[str] = None):
        if not self._enabled:
            return
        self._add_event(DebugEvent(str(uuid4()), EventType.MEMORY_RETRIEVE, time.time(), agent_id,
                                   {'memory_id': memory_id, 'rounds': rounds, 'message_count': message_count}))

    def track_memory_clear(self, memory_id: str, agent_id: Optional[str] = None):
        if not self._enabled:
            return
        self._add_event(DebugEvent(str(uuid4()), EventType.MEMORY_CLEAR, time.time(), agent_id,
                                   {'memory_id': memory_id}))

    # ==================== 其他 ====================

    def track_tool_call(self,
                        tool_name: str,
                        args: Dict,
                        result: Any = None,
                        duration_ms: float = 0,
                        error: Optional[str] = None,
                        agent_id: Optional[str] = None):
        if not self._enabled:
            return

        self._add_event(DebugEvent(str(uuid4()),
                                   EventType.TOOL_CALL,
                                   time.time(),
                                   agent_id,
                                   {'tool_name': tool_name, 'args': args, 'result_preview': str(result)[:500] if result else None,
                                    'duration_ms': duration_ms, 'error': error}))

    def track_custom(self, name: str, data: Dict = None, agent_id: Optional[str] = None):
        if not self._enabled:
            return
        self._add_event(DebugEvent(str(uuid4()), EventType.CUSTOM, time.time(), agent_id,
                                   {'name': name, **(data or {})}))

    # ==================== 查询 ====================

    def get_events(self, event_type: Optional[str] = None, agent_id: Optional[str] = None,
                   since_seq: int = 0, limit: int = 100) -> List[Dict]:
        with self._data_lock:
            events = self._events[since_seq:] if since_seq > 0 else self._events
            if event_type:
                events = [e for e in events if e.event_type.value == event_type]
            if agent_id:
                events = [e for e in events if e.agent_id == agent_id]
            return [e.to_dict() for e in events[-limit:]]

    def get_agents(self) -> List[Dict]:
        with self._data_lock:
            return [a.to_dict() for a in self._agents.values()]

    def get_agent(self, agent_id: str) -> Optional[Dict]:
        with self._data_lock:
            return self._agents[agent_id].to_dict() if agent_id in self._agents else None

    def get_llm_calls(self, agent_id: Optional[str] = None, limit: int = 100) -> List[Dict]:
        with self._data_lock:
            calls = list(self._llm_calls.values())
            if agent_id:
                calls = [c for c in calls if c.agent_id == agent_id]
            calls.sort(key=lambda x: x.start_time, reverse=True)
            return [c.to_dict() for c in calls[:limit]]

    def get_llm_call(self, call_id: str) -> Optional[Dict]:
        with self._data_lock:
            return self._llm_calls[call_id].to_dict() if call_id in self._llm_calls else None

    def get_call_graph(self) -> Dict:
        with self._data_lock:
            nodes = [{'id': a.agent_id, 'label': f"{a.agent_type}\\n{a.agent_id[:8]}", 'type': a.agent_type}
                     for a in self._agents.values()]
            edges = [{'source': a.parent_id, 'target': a.agent_id} for a in self._agents.values() if a.parent_id]
            return {'nodes': nodes, 'edges': edges}

    def get_stats(self) -> Dict:
        with self._data_lock:
            return {**self._stats, 'active_agents': len(self._agents), 'event_seq': self._event_seq}

    @property
    def event_seq(self) -> int:
        return self._event_seq


# 全局实例
tracer = DebugTracer()

