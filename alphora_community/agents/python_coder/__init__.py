"""
Python Coder Agent - 代码生成与执行智能体

基于 Alphora Sandbox 提供 Python 代码生成、执行、自动修复能力。

快速开始:
    from alphora.sandbox import Sandbox
    from alphora_community.agents.python_coder import PythonCoderAgent
    
    async with Sandbox.create_local() as sandbox:
        agent = PythonCoderAgent(sandbox=sandbox)
        
        # 执行单步代码
        result = await agent.execute_code_step(
            description="查看数据结构",
            code="import pandas as pd; print(pd.read_excel('data.xlsx').head())"
        )
        
        # 或执行完整任务
        result = await agent.execute_python_task(
            thought="使用 pandas 读取数据并按城市分组统计",
            query="计算每个城市的销售总额",
            data_insights="文件: sales.xlsx, 列: ['城市', '销售额', '日期']",
        )

核心功能:
- execute_code_step: 执行单步代码（推荐用于 Agent 工具调用）
- execute_python_task: 完整任务流程（生成→执行→修复→总结）
- generate_code: 根据需求生成代码
- fix_code: 修复执行失败的代码
"""

__version__ = "1.0.0"

from .agent import PythonCoderAgent, CodeExecutionResult
from .utils import (
    extract_code_block,
    extract_imports,
    detect_missing_packages,
    format_error_context,
    sanitize_code,
    get_code_hash,
    parse_traceback,
    suggest_fixes,
)
from .prompts import (
    CODER_SYSTEM_PROMPT,
    CODER_TASK_TEMPLATE,
    FIXER_SYSTEM_PROMPT,
    FIXER_TASK_TEMPLATE,
    ANALYZER_SYSTEM_PROMPT,
    SUMMARY_TASK_TEMPLATE,
)

__all__ = [
    # 主类
    'PythonCoderAgent',
    'CodeExecutionResult',
    
    # 工具函数
    'extract_code_block',
    'extract_imports',
    'detect_missing_packages',
    'format_error_context',
    'sanitize_code',
    'get_code_hash',
    'parse_traceback',
    'suggest_fixes',
    
    # 提示词
    'CODER_SYSTEM_PROMPT',
    'CODER_TASK_TEMPLATE',
    'FIXER_SYSTEM_PROMPT',
    'FIXER_TASK_TEMPLATE',
    'ANALYZER_SYSTEM_PROMPT',
    'SUMMARY_TASK_TEMPLATE',
]
