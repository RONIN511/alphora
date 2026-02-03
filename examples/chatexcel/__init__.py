"""
ChatExcel - Excel 数据分析智能体示例

基于 Alphora 框架和 alphora_community 组件构建的完整数据分析 Agent 示例。

快速开始:

    方式 1: 编程调用
    
    from chatexcel import ChatExcel
    from alphora.sandbox import Sandbox
    
    async with Sandbox.create_local() as sandbox:
        agent = ChatExcel(sandbox=sandbox)
        
        # 上传文件到沙箱
        await sandbox.write_file("sales.xlsx", open("sales.xlsx", "rb").read())
        
        # 开始对话
        response = await agent.chat("帮我分析这个销售数据")
        print(response)
    
    方式 2: API 服务
    
    # 启动服务
    uvicorn chatexcel.server:app --host 0.0.0.0 --port 8000
    
    # 调用 API
    curl -X POST http://localhost:8000/chat \\
        -H "Content-Type: application/json" \\
        -d '{"message": "帮我分析销售数据"}'

核心能力:
- 📊 数据查看 - 预览 Excel/CSV 内容和结构
- 📈 数据分析 - Python 代码执行，支持 pandas、numpy 等
- 🔍 联网搜索 - 博查 API 实时搜索
- 📝 文件生成 - 输出分析报告和处理后的数据

依赖的社区组件:
- alphora_community.agents.python_coder
- alphora_community.agents.file_viewer
- alphora_community.agents.internet_search
- alphora_community.agents.memory_manager
"""

__version__ = "1.0.0"

from .main import ChatExcel
from .prompts import CONTROL_PROMPT, THINKING_PROMPT, WELCOME_MESSAGE

__all__ = [
    'ChatExcel',
    'CONTROL_PROMPT',
    'THINKING_PROMPT',
    'WELCOME_MESSAGE',
]
