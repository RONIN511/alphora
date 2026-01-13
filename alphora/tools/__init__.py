"""
alphora.tools - AI Agent 工具和技能框架

一个优雅、强大、易用的 AI Agent 工具框架。

核心概念：
- Tool: 可被 LLM 调用的原子操作
- Skill: 包含工具 + 提示词 + 上下文的完整能力单元

设计原则：
1. 声明式定义 - @tool / @agent_tool / @skill
2. 自动推断 - 从类型注解和 docstring 生成 Schema
3. 原生集成 - 利用 LLM 的 Function Calling
4. 可组合 - Skills 可以灵活组合
5. 状态管理 - SkillContext 统一管理上下文

Quick Start:
    # 1. 定义工具
    from alphora.tools import tool

    @tool
    async def search(query: str) -> str:
        '''搜索互联网

        Args:
            query: 搜索关键词
        '''
        return await do_search(query)

    # 2. 定义 Skill
    from alphora.tools import Skill, SkillMetadata

    class SearchSkill(Skill):
        metadata = SkillMetadata(
            name="search",
            triggers=["搜索", "查找"]
        )

        def setup_tools(self):
            return [search]

        def get_system_prompt(self):
            return "你是搜索助手..."

    # 3. 创建执行器
    from alphora.tools import ToolExecutor

    executor = ToolExecutor([search])
    result = await executor.execute("search", query="Python")
"""

__version__ = "0.2.0"

# ==================== 核心类型 ====================
from .types import (
    # 状态
    ToolStatus,

    # 结果
    ToolResult,

    # 调用
    ToolCall,

    # Schema
    ToolParameter,
    ToolSchema,

    # 配置
    ToolConfig,
)

# ==================== 工具定义 ====================
from .tool import (
    # 基类
    Tool,
    FunctionTool,
    AgentTool,

    # 装饰器
    tool,
    agent_tool,

    # 工具集
    ToolSet,

    # 辅助函数
    create_tool,
)

# ==================== Skill 技能 ====================
from .skill import (
    # 基类
    Skill,
    FunctionSkill,

    # 元数据和上下文
    SkillMetadata,
    SkillContext,

    # 注册表
    SkillRegistry,

    # 装饰器
    skill,

    # 组合器
    SkillComposer,

    # 预置模板
    ChatSkill,
    DataQuerySkillTemplate,
)

# ==================== 执行器 ====================
from .executor import (
    ToolExecutor,
    ToolConversationExecutor,
    ExecutionTrace,
    ExecutionTracer,
)

# ==================== 便捷导出 ====================

__all__ = [
    # 版本
    "__version__",

    # 类型
    "ToolStatus",
    "ToolResult",
    "ToolCall",
    "ToolParameter",
    "ToolSchema",
    "ToolConfig",

    # 工具
    "Tool",
    "FunctionTool",
    "AgentTool",
    "tool",
    "agent_tool",
    "ToolSet",
    "create_tool",

    # Skill
    "Skill",
    "FunctionSkill",
    "SkillMetadata",
    "SkillContext",
    "SkillRegistry",
    "skill",
    "SkillComposer",
    "ChatSkill",
    "DataQuerySkillTemplate",

    # 执行器
    "ToolExecutor",
    "ToolConversationExecutor",
    "ExecutionTrace",
    "ExecutionTracer",
]
