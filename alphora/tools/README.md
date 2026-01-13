# Alphora Tools

AI Agent 工具和技能框架，为 Alphora 框架提供声明式的工具定义和能力封装。

## 核心概念

| 概念 | 说明 | 类比 |
|------|------|------|
| **Tool** | 可被 LLM 调用的原子操作 | 厨具（刀、锅） |
| **Skill** | 工具 + 提示词 + 上下文的完整能力 | 菜谱（红烧肉做法） |

## 快速开始

### 1. 定义工具

```python
from alphora.tools import tool

@tool
async def search(query: str, limit: int = 10) -> str:
    """搜索互联网
    
    Args:
        query: 搜索关键词
        limit: 结果数量
    """
    return await do_search(query, limit)
```

### 2. Agent 作为工具

```python
from alphora.tools import agent_tool, ToolResult

@agent_tool(
    name="data_query",
    requires=['dacos_client', 'source_id']  # 声明依赖
)
class DataQueryAgent:
    """数据查询智能体"""
    
    async def run(self, query: str) -> ToolResult:
        # 框架自动注入依赖
        return ToolResult.ok({"sql": "...", "data": [...]})
```

### 3. 定义 Skill

```python
from alphora.tools import Skill, SkillMetadata

class DataAnalysisSkill(Skill):
    """数据分析技能"""
    
    metadata = SkillMetadata(
        name="data_analysis",
        description="数据查询和可视化",
        triggers=["查询", "分析", "统计", "多少"]
    )
    
    def setup_tools(self):
        return [search, DataQueryAgent]
    
    def get_system_prompt(self):
        return "你是数据分析助手..."
```

### 4. 执行工具

```python
from alphora.tools import ToolExecutor

executor = ToolExecutor([search, calc])

# 单工具执行
result = await executor.execute("search", query="Python")

# 解析 LLM 响应并执行
tool_calls = executor.parse_llm_response(llm_response)
results = await executor.execute_calls(tool_calls)
```

## 模块说明

| 模块 | 说明 |
|------|------|
| `types.py` | 核心类型：ToolResult, ToolCall, ToolSchema |
| `tool.py` | 工具定义：@tool, @agent_tool, Tool 基类 |
| `skill.py` | 技能封装：Skill, SkillContext, SkillComposer |
| `executor.py` | 执行引擎：ToolExecutor, 支持并行执行和追踪 |

## 主要特性

- **声明式定义** - 使用装饰器，自动从类型注解生成 Schema
- **原生集成** - 支持 OpenAI / Anthropic Function Calling
- **依赖注入** - `@agent_tool(requires=[...])` 自动注入配置
- **上下文管理** - SkillContext 统一管理状态
- **可组合** - Skills 可以灵活组合到不同 Agent

## 对比改进

| 之前 | 现在 |
|------|------|
| Prompt 模拟工具路由 | LLM 原生 Function Calling |
| if/else 手动分发 | 框架自动路由 |
| 手动传递配置 | 声明式依赖注入 |
| 状态散落各处 | SkillContext 统一管理 |
| 能力硬编码 | Skill 封装可复用 |

