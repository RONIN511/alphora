"""
Alphora Debugger

用法：
    agent = BaseAgent(llm=llm, debugger=True)
    # 访问 http://localhost:9527/
"""

from .tracer import tracer, DebugTracer, DebugEvent, EventType

__version__ = "1.0.0"
__all__ = ["tracer", "DebugTracer", "DebugEvent", "EventType"]