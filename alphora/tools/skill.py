"""
alphora.tools.skill - Skill 技能模块

设计目标：
Skill 是比 Tool 更高层次的抽象，代表完成特定任务的完整能力。

概念对比：
| 概念 | 类比 | 包含内容 |
|------|------|----------|
| Tool | 厨具 | 单一操作（查询、计算） |
| Skill | 菜谱 | 工具 + 流程 + 知识 + 提示词 |

Skill 包含：
1. 一组相关工具
2. 系统提示词（领域知识）
3. 上下文管理
4. 触发条件
5. 执行策略

解决的痛点：
- 之前：所有逻辑硬编码在 Agent 里，无法复用
- 现在：将能力封装为 Skill，可以灵活组合到不同 Agent
"""

from __future__ import annotations

import re
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type, Union
from dataclasses import dataclass, field

from .types import ToolResult, ToolConfig
from .tool import Tool, FunctionTool, ToolSet, tool as tool_decorator, AgentTool

logger = logging.getLogger(__name__)


# ==================== Skill 元数据 ====================

@dataclass
class SkillMetadata:
    """
    Skill 元数据定义

    Attributes:
        name: 技能名称
        description: 技能描述
        triggers: 触发关键词列表，用于自动激活
        tags: 标签，用于分类和搜索
        priority: 优先级，多个 Skill 匹配时的选择依据
        exclusive: 是否排他，True 表示激活后不再匹配其他 Skill
    """
    name: str
    description: str = ""
    version: str = "1.0.0"

    # 触发条件
    triggers: List[str] = field(default_factory=list)
    trigger_patterns: List[str] = field(default_factory=list)  # 正则模式

    # 分类
    tags: List[str] = field(default_factory=list)

    # 优先级和排他性
    priority: int = 0
    exclusive: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "triggers": self.triggers,
            "tags": self.tags,
            "priority": self.priority,
        }


# ==================== Skill 上下文 ====================

@dataclass
class SkillContext:
    """
    Skill 执行上下文

    用于在 Skill 的多个工具调用之间共享状态

    解决痛点：
    - 之前：状态分散在 get_config/update_config 里
    - 现在：统一的上下文管理
    """
    # 会话信息
    session_id: Optional[str] = None
    user_query: Optional[str] = None

    # 共享数据
    data: Dict[str, Any] = field(default_factory=dict)

    # 中间结果
    intermediate_results: List[Any] = field(default_factory=list)

    # 执行历史
    execution_history: List[Dict[str, Any]] = field(default_factory=list)

    def get(self, key: str, default: Any = None) -> Any:
        """获取数据"""
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """设置数据"""
        self.data[key] = value

    def add_result(self, tool_name: str, result: Any) -> None:
        """添加中间结果"""
        self.intermediate_results.append({
            "tool": tool_name,
            "result": result,
        })
        self.execution_history.append({
            "tool": tool_name,
            "result_type": type(result).__name__,
        })

    def get_last_result(self, tool_name: Optional[str] = None) -> Any:
        """获取最后一个结果"""
        if not self.intermediate_results:
            return None

        if tool_name:
            for item in reversed(self.intermediate_results):
                if item["tool"] == tool_name:
                    return item["result"]
            return None

        return self.intermediate_results[-1]["result"]


# ==================== Skill 基类 ====================

class Skill(ABC):
    """
    Skill 基类

    Skill 是一个完整的能力单元，包含：
    - 工具集合
    - 系统提示词
    - 上下文管理
    - 触发逻辑

    Examples:
        >>> class DataAnalysisSkill(Skill):
        ...     '''数据分析技能'''
        ...
        ...     metadata = SkillMetadata(
        ...         name="data_analysis",
        ...         description="数据查询、分析和可视化",
        ...         triggers=["查询", "分析", "统计", "多少", "哪些"]
        ...     )
        ...
        ...     def setup_tools(self) -> List[Tool]:
        ...         @tool
        ...         async def query_data(sql: str) -> dict:
        ...             '''执行数据查询'''
        ...             ...
        ...
        ...         @tool
        ...         async def visualize(data: dict, chart_type: str) -> str:
        ...             '''生成可视化图表'''
        ...             ...
        ...
        ...         return [query_data, visualize]
        ...
        ...     def get_system_prompt(self) -> str:
        ...         return '''你是数据分析助手，可以：
        ...         1. 执行数据查询
        ...         2. 生成可视化图表
        ...         请根据用户需求选择合适的工具。'''
    """

    # 子类应定义
    metadata: SkillMetadata = None

    def __init__(self):
        self._tools: Optional[List[Tool]] = None
        self._context: Optional[SkillContext] = None
        self._config: Optional[ToolConfig] = None

        # 自动设置元数据
        if self.metadata is None:
            self.metadata = SkillMetadata(
                name=self._infer_name(),
                description=self.__doc__ or "",
            )

    def _infer_name(self) -> str:
        """从类名推断名称"""
        name = self.__class__.__name__
        if name.endswith('Skill'):
            name = name[:-5]
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    # ==================== 抽象方法 ====================

    @abstractmethod
    def setup_tools(self) -> List[Tool]:
        """
        设置工具列表

        子类必须实现，返回此 Skill 使用的工具

        Returns:
            工具列表，可以包含：
            - FunctionTool（@tool 装饰的函数）
            - AgentTool（@agent_tool 装饰的 Agent）
            - Tool 子类实例
        """
        pass

    # ==================== 可选重写方法 ====================

    def get_system_prompt(self) -> Optional[str]:
        """
        获取系统提示词

        返回此 Skill 的专属系统提示词，会被添加到 Agent 的系统提示词中
        """
        return None

    def get_context_prompt(self) -> Optional[str]:
        """
        获取上下文提示词

        基于当前上下文生成动态提示词
        """
        return None

    def should_activate(self, query: str, context: Optional[Dict] = None) -> bool:
        """
        判断是否应该激活此 Skill

        默认实现：检查触发关键词和正则模式
        子类可重写以实现更复杂的激活逻辑

        Args:
            query: 用户查询
            context: 额外上下文（如会话历史）

        Returns:
            是否应该激活
        """
        query_lower = query.lower()

        # 检查关键词
        if self.metadata.triggers:
            for trigger in self.metadata.triggers:
                if trigger.lower() in query_lower:
                    return True

        # 检查正则模式
        if self.metadata.trigger_patterns:
            for pattern in self.metadata.trigger_patterns:
                if re.search(pattern, query, re.IGNORECASE):
                    return True

        # 没有触发条件则默认激活
        if not self.metadata.triggers and not self.metadata.trigger_patterns:
            return True

        return False

    def on_activate(self, query: str, context: SkillContext) -> None:
        """Skill 被激活时的回调"""
        pass

    def on_deactivate(self) -> None:
        """Skill 被停用时的回调"""
        pass

    def on_tool_result(self, tool_name: str, result: ToolResult) -> None:
        """工具执行完成的回调"""
        if self._context:
            self._context.add_result(tool_name, result)

    # ==================== 工具管理 ====================

    @property
    def tools(self) -> List[Tool]:
        """获取工具列表"""
        if self._tools is None:
            self._tools = self.setup_tools()
            # 配置工具
            if self._config:
                for t in self._tools:
                    t.configure(self._config)
        return self._tools

    @property
    def context(self) -> SkillContext:
        """获取上下文"""
        if self._context is None:
            self._context = SkillContext()
        return self._context

    def set_context(self, context: SkillContext) -> None:
        """设置上下文"""
        self._context = context

    def configure(self, config: ToolConfig) -> Skill:
        """配置 Skill"""
        self._config = config
        # 传递给工具
        for t in self.tools:
            t.configure(config)
        return self

    # ==================== Schema 生成 ====================

    def to_openai_tools(self) -> List[Dict[str, Any]]:
        """转换为 OpenAI 格式"""
        return [t.to_openai() for t in self.tools]

    def to_anthropic_tools(self) -> List[Dict[str, Any]]:
        """转换为 Anthropic 格式"""
        return [t.to_anthropic() for t in self.tools]

    def __repr__(self) -> str:
        return f"<Skill: {self.metadata.name}>"


# ==================== 函数式 Skill ====================

class FunctionSkill(Skill):
    """
    函数式 Skill 定义

    用于快速创建简单的 Skill，无需继承

    Examples:
        >>> skill = FunctionSkill(
        ...     name="math",
        ...     description="数学计算",
        ...     tools=[add_tool, multiply_tool],
        ...     triggers=["计算", "加", "乘"],
        ...     system_prompt="你是数学计算助手..."
        ... )
    """

    def __init__(
            self,
            name: str,
            description: str = "",
            tools: Optional[List[Tool]] = None,
            triggers: Optional[List[str]] = None,
            system_prompt: Optional[str] = None,
            priority: int = 0,
    ):
        self._provided_tools = tools or []
        self._system_prompt = system_prompt

        self.metadata = SkillMetadata(
            name=name,
            description=description,
            triggers=triggers or [],
            priority=priority,
        )

        super().__init__()

    def setup_tools(self) -> List[Tool]:
        return self._provided_tools

    def get_system_prompt(self) -> Optional[str]:
        return self._system_prompt


# ==================== Skill 注册表 ====================

class SkillRegistry:
    """
    Skill 注册表

    管理所有可用的 Skills，支持：
    - 按名称获取
    - 按查询匹配激活
    - 按标签搜索
    """

    def __init__(self):
        self._skills: Dict[str, Skill] = {}

    def register(self, skill: Skill) -> SkillRegistry:
        """注册 Skill"""
        if skill.metadata.name in self._skills:
            logger.warning(f"Skill '{skill.metadata.name}' already registered, overwriting")
        self._skills[skill.metadata.name] = skill
        return self

    def unregister(self, name: str) -> bool:
        """注销 Skill"""
        if name in self._skills:
            del self._skills[name]
            return True
        return False

    def get(self, name: str) -> Optional[Skill]:
        """按名称获取 Skill"""
        return self._skills.get(name)

    def list(self) -> List[Skill]:
        """列出所有 Skills"""
        return list(self._skills.values())

    def find_by_query(
            self,
            query: str,
            context: Optional[Dict] = None,
            max_skills: int = 3,
    ) -> List[Skill]:
        """
        根据查询找到应该激活的 Skills

        Args:
            query: 用户查询
            context: 额外上下文
            max_skills: 最大返回数量

        Returns:
            按优先级排序的 Skill 列表
        """
        matched = []

        for skill in self._skills.values():
            if skill.should_activate(query, context):
                matched.append(skill)

        # 按优先级排序
        matched.sort(key=lambda s: s.metadata.priority, reverse=True)

        # 处理排他性
        result = []
        for skill in matched:
            result.append(skill)
            if skill.metadata.exclusive:
                break
            if len(result) >= max_skills:
                break

        return result

    def find_by_tag(self, tag: str) -> List[Skill]:
        """按标签查找 Skills"""
        return [s for s in self._skills.values() if tag in s.metadata.tags]

    def get_all_tools(self) -> List[Tool]:
        """获取所有 Skills 的所有工具"""
        all_tools = []
        for skill in self._skills.values():
            all_tools.extend(skill.tools)
        return all_tools

    def __contains__(self, name: str) -> bool:
        return name in self._skills

    def __len__(self) -> int:
        return len(self._skills)

    def __iter__(self):
        return iter(self._skills.values())


# ==================== Skill 装饰器 ====================

def skill(
        name: Optional[str] = None,
        description: Optional[str] = None,
        triggers: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        priority: int = 0,
):
    """
    Skill 装饰器

    将一个类装饰为 Skill，自动收集其中的 @tool 方法

    Examples:
        >>> @skill(name="math", triggers=["计算", "求"])
        ... class MathSkill:
        ...     '''数学计算技能'''
        ...
        ...     @tool
        ...     def add(self, a: int, b: int) -> int:
        ...         '''两数相加'''
        ...         return a + b
        ...
        ...     @tool
        ...     def multiply(self, a: int, b: int) -> int:
        ...         '''两数相乘'''
        ...         return a * b
    """
    def decorator(cls):
        # 收集 @tool 装饰的方法
        tools = []
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name, None)
            if isinstance(attr, Tool):
                tools.append(attr)

        # 获取系统提示词方法
        system_prompt = None
        if hasattr(cls, 'get_system_prompt'):
            instance = cls()
            prompt_method = getattr(instance, 'get_system_prompt', None)
            if callable(prompt_method):
                system_prompt = prompt_method()

        skill_name = name or cls.__name__.lower().replace('skill', '')
        skill_desc = description or cls.__doc__ or ""

        return FunctionSkill(
            name=skill_name,
            description=skill_desc,
            tools=tools,
            triggers=triggers,
            system_prompt=system_prompt,
            priority=priority,
        )

    return decorator


# ==================== 预置 Skill 模板 ====================

class ChatSkill(Skill):
    """
    通用对话技能

    处理不需要工具的普通对话
    """

    metadata = SkillMetadata(
        name="chat",
        description="普通对话和闲聊",
        triggers=[],  # 空触发器，作为兜底
        priority=-100,  # 最低优先级
    )

    def setup_tools(self) -> List[Tool]:
        return []  # 对话不需要工具

    def get_system_prompt(self) -> str:
        return "你是一个友好的助手，可以进行日常对话。"

    def should_activate(self, query: str, context: Optional[Dict] = None) -> bool:
        # 作为兜底，始终可以激活
        return True


class DataQuerySkillTemplate(Skill):
    """
    数据查询技能模板

    基于你的实际业务场景设计

    使用方式：
    1. 继承此类
    2. 实现 create_query_tool() 和 create_viz_tool()
    3. 可选重写 get_system_prompt()
    """

    metadata = SkillMetadata(
        name="data_query",
        description="数据查询和可视化",
        triggers=["查询", "统计", "分析", "多少", "哪些", "占比", "趋势", "对比"],
        trigger_patterns=[
            r"有多少",
            r".*的数量",
            r".*的比例",
            r"哪个.*最",
        ],
        priority=10,
    )

    @abstractmethod
    def create_query_tool(self) -> Tool:
        """创建数据查询工具"""
        pass

    @abstractmethod
    def create_viz_tool(self) -> Tool:
        """创建可视化工具"""
        pass

    def setup_tools(self) -> List[Tool]:
        return [
            self.create_query_tool(),
            self.create_viz_tool(),
        ]

    def get_system_prompt(self) -> str:
        return """你是数据分析助手，可以执行以下操作：

1. **数据查询** - 根据用户问题生成 SQL 并执行查询
2. **数据可视化** - 将查询结果生成图表

工作流程：
1. 理解用户的数据需求
2. 调用 data_query 工具执行查询
3. 如果需要可视化，调用 visualize 工具生成图表
4. 总结分析结果

注意事项：
- 如果查询结果为空，说明筛选条件可能过于严格
- 生成图表时选择最合适的图表类型"""


# ==================== Skill 组合器 ====================

class SkillComposer:
    """
    Skill 组合器

    用于将多个 Skills 组合成一个复合能力

    Examples:
        >>> composer = SkillComposer()
        >>> composer.add(DataQuerySkill())
        >>> composer.add(VizSkill())
        >>> composer.add(ChatSkill())
        >>>
        >>> # 获取所有工具
        >>> tools = composer.get_all_tools()
        >>>
        >>> # 获取组合的系统提示词
        >>> system_prompt = composer.get_combined_prompt()
    """

    def __init__(self):
        self._skills: List[Skill] = []
        self._registry = SkillRegistry()

    def add(self, skill: Skill) -> SkillComposer:
        """添加 Skill"""
        self._skills.append(skill)
        self._registry.register(skill)
        return self

    def remove(self, name: str) -> bool:
        """移除 Skill"""
        self._skills = [s for s in self._skills if s.metadata.name != name]
        return self._registry.unregister(name)

    def activate_for_query(
            self,
            query: str,
            context: Optional[Dict] = None,
    ) -> List[Skill]:
        """根据查询激活相关 Skills"""
        return self._registry.find_by_query(query, context)

    def get_all_tools(self) -> List[Tool]:
        """获取所有工具"""
        return self._registry.get_all_tools()

    def get_active_tools(self, query: str) -> List[Tool]:
        """获取激活 Skills 的工具"""
        active_skills = self.activate_for_query(query)
        tools = []
        for skill in active_skills:
            tools.extend(skill.tools)
        return tools

    def get_combined_prompt(self, active_only: bool = False, query: str = "") -> str:
        """获取组合的系统提示词"""
        skills = self.activate_for_query(query) if active_only else self._skills

        prompts = []
        for skill in skills:
            prompt = skill.get_system_prompt()
            if prompt:
                prompts.append(f"## {skill.metadata.name}\n{prompt}")

        return "\n\n".join(prompts)

    @property
    def skills(self) -> List[Skill]:
        return self._skills

    @property
    def registry(self) -> SkillRegistry:
        return self._registry

