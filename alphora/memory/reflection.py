"""
记忆反思模块

使用LLM对记忆进行：
- 摘要生成
- 关键信息提取
- 重要性评估
- 洞察发现
"""

from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
import time
import json
import re
import asyncio

from alphora.memory.memory_unit import MemoryUnit, MemoryType, create_memory


@dataclass
class ReflectionResult:
    """反思结果"""
    summary: str
    key_points: List[str]
    importance_scores: Dict[str, float]  # memory_id -> importance
    insights: List[str]
    metadata: Dict[str, Any]


class MemoryReflector:
    """
    记忆反思器
    
    使用LLM对记忆进行分析、摘要和反思。
    
    使用示例:
    ```python
    from alphora.models import OpenAILike
    
    llm = OpenAILike(...)
    reflector = MemoryReflector(llm)
    
    # 生成摘要
    summary = await reflector.summarize(memories)
    
    # 提取关键信息
    key_info = await reflector.extract_key_info(memories)
    
    # 评估重要性
    importance = await reflector.evaluate_importance(memory, context)
    
    # 完整反思
    reflection = await reflector.reflect(memories)
    ```
    """
    
    # 摘要提示模板
    SUMMARY_PROMPT = """请对以下对话历史生成一个简洁的摘要。

对话历史：
{history}

要求：
1. 摘要应该简洁明了，不超过{max_length}个字
2. 突出重要的信息和结论
3. 保持客观，不添加推测

摘要："""
    
    # 关键信息提取提示
    KEY_INFO_PROMPT = """请从以下对话中提取关键信息。

对话历史：
{history}

请以JSON格式输出，包含以下字段：
- user_preferences: 用户偏好列表
- important_facts: 重要事实列表
- action_items: 待办事项列表
- topics: 讨论的主题列表

只输出JSON，不要其他内容："""
    
    # 重要性评估提示
    IMPORTANCE_PROMPT = """请评估以下记忆的重要性。

记忆内容：
{content}

上下文（最近的对话）：
{context}

请给出0-1之间的重要性分数，并简要说明理由。

输出格式（JSON）：
{{"importance": 0.X, "reason": "..."}}

只输出JSON："""
    
    # 反思提示
    REFLECTION_PROMPT = """请对以下对话历史进行深度反思和分析。

对话历史：
{history}

请分析：
1. 这段对话的主要目的是什么？
2. 有哪些重要的信息或决策？
3. 用户有什么特别的需求或偏好？
4. 有什么值得记住的洞察？

以JSON格式输出：
{{
    "purpose": "对话目的",
    "key_decisions": ["决策1", "决策2"],
    "user_needs": ["需求1", "需求2"],
    "insights": ["洞察1", "洞察2"],
    "summary": "整体摘要"
}}

只输出JSON："""
    
    def __init__(
        self,
        llm: Any,
        max_summary_length: int = 200,
        max_context_memories: int = 20
    ):
        """
        Args:
            llm: LLM实例，需要有ainvoke方法
            max_summary_length: 摘要最大长度
            max_context_memories: 上下文最大记忆数
        """
        self.llm = llm
        self.max_summary_length = max_summary_length
        self.max_context_memories = max_context_memories
    
    def _format_memories(self, memories: List[MemoryUnit]) -> str:
        """格式化记忆为文本"""
        lines = []
        for mem in memories:
            role = mem.get_role()
            content = mem.get_content_text()
            timestamp = mem.formatted_timestamp(include_second=False)
            lines.append(f"[{timestamp}] {role}: {content}")
        return "\n".join(lines)
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """解析LLM的JSON响应"""
        # 尝试提取JSON部分
        response = response.strip()
        
        # 移除可能的markdown代码块标记
        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(lines[1:-1])
        
        # 尝试找到JSON对象
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        # 如果解析失败，返回空字典
        return {}
    
    async def summarize(
        self,
        memories: List[MemoryUnit],
        style: str = "brief",
        max_length: Optional[int] = None
    ) -> str:
        """
        生成记忆摘要
        
        Args:
            memories: 记忆列表
            style: 摘要风格 (brief/detailed)
            max_length: 最大长度
            
        Returns:
            摘要文本
        """
        if not memories:
            return ""
        
        # 限制记忆数量
        memories = sorted(memories, key=lambda m: m.timestamp)[-self.max_context_memories:]
        
        history = self._format_memories(memories)
        length = max_length or self.max_summary_length
        
        if style == "detailed":
            length *= 2
        
        prompt = self.SUMMARY_PROMPT.format(
            history=history,
            max_length=length
        )
        
        try:
            response = await self.llm.ainvoke(message=prompt)
            return response.strip()
        except Exception as e:
            # 如果LLM调用失败，返回简单摘要
            return f"对话包含{len(memories)}条记忆，涉及{len(set(m.get_role() for m in memories))}个角色。"
    
    async def extract_key_info(
        self,
        memories: List[MemoryUnit]
    ) -> Dict[str, List[str]]:
        """
        提取关键信息
        
        Args:
            memories: 记忆列表
            
        Returns:
            关键信息字典
        """
        if not memories:
            return {
                "user_preferences": [],
                "important_facts": [],
                "action_items": [],
                "topics": []
            }
        
        memories = sorted(memories, key=lambda m: m.timestamp)[-self.max_context_memories:]
        history = self._format_memories(memories)
        
        prompt = self.KEY_INFO_PROMPT.format(history=history)
        
        try:
            response = await self.llm.ainvoke(message=prompt)
            result = self._parse_json_response(response)
            
            # 确保返回正确的结构
            return {
                "user_preferences": result.get("user_preferences", []),
                "important_facts": result.get("important_facts", []),
                "action_items": result.get("action_items", []),
                "topics": result.get("topics", [])
            }
        except Exception as e:
            return {
                "user_preferences": [],
                "important_facts": [],
                "action_items": [],
                "topics": []
            }
    
    async def evaluate_importance(
        self,
        memory: MemoryUnit,
        context: Optional[List[MemoryUnit]] = None
    ) -> Tuple[float, str]:
        """
        评估单条记忆的重要性
        
        Args:
            memory: 要评估的记忆
            context: 上下文记忆
            
        Returns:
            (重要性分数, 原因)
        """
        content = f"{memory.get_role()}: {memory.get_content_text()}"
        
        context_text = ""
        if context:
            context = sorted(context, key=lambda m: m.timestamp)[-5:]
            context_text = self._format_memories(context)
        
        prompt = self.IMPORTANCE_PROMPT.format(
            content=content,
            context=context_text or "（无上下文）"
        )
        
        try:
            response = await self.llm.ainvoke(message=prompt)
            result = self._parse_json_response(response)
            
            importance = float(result.get("importance", 0.5))
            importance = max(0.0, min(1.0, importance))
            reason = result.get("reason", "")
            
            return importance, reason
        except Exception as e:
            return 0.5, "评估失败"
    
    async def reflect(
        self,
        memories: List[MemoryUnit]
    ) -> ReflectionResult:
        """
        完整反思
        
        Args:
            memories: 记忆列表
            
        Returns:
            反思结果
        """
        if not memories:
            return ReflectionResult(
                summary="",
                key_points=[],
                importance_scores={},
                insights=[],
                metadata={}
            )
        
        memories = sorted(memories, key=lambda m: m.timestamp)[-self.max_context_memories:]
        history = self._format_memories(memories)
        
        prompt = self.REFLECTION_PROMPT.format(history=history)
        
        try:
            response = await self.llm.ainvoke(message=prompt)
            result = self._parse_json_response(response)
            
            return ReflectionResult(
                summary=result.get("summary", ""),
                key_points=result.get("key_decisions", []) + result.get("user_needs", []),
                importance_scores={},  # 可以单独评估
                insights=result.get("insights", []),
                metadata={
                    "purpose": result.get("purpose", ""),
                    "timestamp": time.time()
                }
            )
        except Exception as e:
            return ReflectionResult(
                summary="反思生成失败",
                key_points=[],
                importance_scores={},
                insights=[],
                metadata={"error": str(e)}
            )
    
    async def create_reflection_memory(
        self,
        memories: List[MemoryUnit],
        memory_id: str = "default"
    ) -> Optional[MemoryUnit]:
        """
        创建反思记忆单元
        
        Args:
            memories: 源记忆列表
            memory_id: 记忆ID
            
        Returns:
            反思记忆单元
        """
        reflection = await self.reflect(memories)
        
        if not reflection.summary:
            return None
        
        # 构建反思内容
        content_parts = [f"[反思摘要] {reflection.summary}"]
        
        if reflection.key_points:
            content_parts.append(f"[关键点] " + "; ".join(reflection.key_points[:3]))
        
        if reflection.insights:
            content_parts.append(f"[洞察] " + "; ".join(reflection.insights[:2]))
        
        content = " | ".join(content_parts)
        
        # 创建反思记忆
        memory = create_memory(
            role="system",
            content=content,
            importance=0.8,  # 反思记忆通常很重要
            tags=["reflection", "summary"],
            memory_type=MemoryType.REFLECTION,
            auto_extract_tags=True
        )
        
        # 记录源记忆ID
        memory.summary_of = [m.unique_id for m in memories]
        memory.metadata["reflection"] = {
            "source_count": len(memories),
            "timestamp": time.time()
        }
        
        return memory


class AutoReflector:
    """
    自动反思器
    
    自动监控记忆并在适当时机触发反思
    """
    
    def __init__(
        self,
        reflector: MemoryReflector,
        threshold: int = 20,
        min_interval: float = 300  # 最小反思间隔（秒）
    ):
        """
        Args:
            reflector: 记忆反思器
            threshold: 触发反思的记忆数量阈值
            min_interval: 最小反思间隔
        """
        self.reflector = reflector
        self.threshold = threshold
        self.min_interval = min_interval
        
        self._last_reflection: Dict[str, float] = {}  # memory_id -> timestamp
        self._memory_counts: Dict[str, int] = {}  # memory_id -> count
    
    def should_reflect(self, memory_id: str, current_count: int) -> bool:
        """判断是否应该反思"""
        # 检查数量阈值
        last_count = self._memory_counts.get(memory_id, 0)
        if current_count - last_count < self.threshold:
            return False
        
        # 检查时间间隔
        last_time = self._last_reflection.get(memory_id, 0)
        if time.time() - last_time < self.min_interval:
            return False
        
        return True
    
    async def maybe_reflect(
        self,
        memories: List[MemoryUnit],
        memory_id: str = "default"
    ) -> Optional[MemoryUnit]:
        """
        根据条件可能触发反思
        
        Args:
            memories: 记忆列表
            memory_id: 记忆ID
            
        Returns:
            反思记忆（如果触发了反思）
        """
        if not self.should_reflect(memory_id, len(memories)):
            return None
        
        # 触发反思
        reflection_memory = await self.reflector.create_reflection_memory(
            memories, memory_id
        )
        
        if reflection_memory:
            self._last_reflection[memory_id] = time.time()
            self._memory_counts[memory_id] = len(memories)
        
        return reflection_memory
    
    def reset(self, memory_id: Optional[str] = None):
        """重置反思状态"""
        if memory_id:
            self._last_reflection.pop(memory_id, None)
            self._memory_counts.pop(memory_id, None)
        else:
            self._last_reflection.clear()
            self._memory_counts.clear()
