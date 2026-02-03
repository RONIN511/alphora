"""
ChatExcel - Excel 数据分析智能体示例

演示如何使用 alphora_community 组件构建完整的数据分析 Agent。

使用示例:
    from chatexcel import ChatExcel
    from alphora.sandbox import Sandbox
    
    async with Sandbox.create_local() as sandbox:
        agent = ChatExcel(sandbox=sandbox)
        response = await agent.chat("分析这个Excel文件的销售数据")
"""

import os
from typing import Optional, List, Dict, Any

from alphora.agent import BaseAgent
from alphora.sandbox import Sandbox

# 导入社区组件
from alphora_community.agents.python_coder import PythonCoderAgent
from alphora_community.agents.file_viewer import FileViewerAgent
from alphora_community.agents.internet_search import InternetSearchAgent

from .prompts import CONTROL_PROMPT, THINKING_PROMPT, WELCOME_MESSAGE


class ChatExcel(BaseAgent):
    """
    ChatExcel - Excel 数据分析智能体
    
    整合文件查看、代码执行、联网搜索等能力，提供完整的表格数据分析服务。
    
    Attributes:
        sandbox: Alphora Sandbox 实例
        file_viewer: 文件查看智能体
        python_coder: 代码执行智能体
        internet_search: 联网搜索智能体
        memory_manager: 记忆管理智能体
    """
    
    def __init__(
        self,
        sandbox: Sandbox,
        bocha_api_key: Optional[str] = None,
        **kwargs
    ):
        """
        初始化 ChatExcel
        
        Args:
            sandbox: Alphora Sandbox 实例
            bocha_api_key: 博查搜索 API Key（可选）
            **kwargs: 传递给 BaseAgent 的参数
        """
        super().__init__(**kwargs)
        
        self.sandbox = sandbox
        
        # 初始化子智能体
        self.file_viewer = FileViewerAgent(
            sandbox=sandbox,
            stream=self.stream,
            llm=self.llm,
        )
        
        self.python_coder = PythonCoderAgent(
            sandbox=sandbox,
            auto_install=True,
            max_fix_attempts=3,
            stream=self.stream,
            llm=self.llm,
        )
        
        self.internet_search = InternetSearchAgent(
            api_key=bocha_api_key,
            stream=self.stream,
            llm=self.llm,
        )

        # 对话状态
        self._data_insights: Dict[str, str] = {}  # 文件名 -> 数据结构信息
        self._history: List[Dict[str, Any]] = []
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """获取可用的工具定义"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "view_file",
                    "description": "查看文件内容、结构或搜索关键词。在分析数据前必须先调用此工具了解数据结构。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_name": {
                                "type": "string",
                                "description": "要查看的文件名"
                            },
                            "purpose": {
                                "type": "string",
                                "enum": ["preview", "structure", "search", "range", "stats"],
                                "description": "查看目的：preview预览、structure结构、search搜索、range范围、stats统计"
                            },
                            "keyword": {
                                "type": "string",
                                "description": "搜索关键词（提供时自动切换为search模式）"
                            },
                            "sheet_name": {
                                "type": "string",
                                "description": "Excel工作表名称"
                            },
                            "max_lines": {
                                "type": "integer",
                                "description": "最大返回行数，默认50"
                            }
                        },
                        "required": ["file_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_code_step",
                    "description": "执行单步Python代码，用于探索式数据分析。每次执行独立，变量不保留。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "description": {
                                "type": "string",
                                "description": "本步骤的目的说明"
                            },
                            "code": {
                                "type": "string",
                                "description": "要执行的Python代码"
                            }
                        },
                        "required": ["description", "code"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_python_task",
                    "description": "执行完整的Python分析任务，自动生成代码、执行、修复错误并总结结果。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "thought": {
                                "type": "string",
                                "description": "解题思路和实现策略"
                            },
                            "query": {
                                "type": "string",
                                "description": "用户的原始任务需求"
                            },
                            "data_insights": {
                                "type": "string",
                                "description": "数据结构信息（文件名、列名、数据类型等）"
                            }
                        },
                        "required": ["thought", "query", "data_insights"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_internet",
                    "description": "联网搜索最新信息，用于获取实时数据或补充知识。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "搜索关键词"
                            },
                            "freshness": {
                                "type": "string",
                                "enum": ["noLimit", "oneDay", "oneWeek", "oneMonth", "oneYear"],
                                "description": "时间范围过滤"
                            }
                        },
                        "required": ["query"]
                    }
                }
            }
        ]
    
    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        执行工具调用
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            工具执行结果
        """
        if tool_name == "view_file":
            result = await self.file_viewer.view_file(**arguments)
            
            # 缓存数据结构信息
            file_name = arguments.get("file_name", "")
            if file_name and result and not result.startswith("❌"):
                self._data_insights[file_name] = result
            
            return result
        
        elif tool_name == "execute_code_step":
            return await self.python_coder.execute_code_step(**arguments)
        
        elif tool_name == "execute_python_task":
            # 补充数据信息
            if "data_insights" not in arguments or not arguments["data_insights"]:
                arguments["data_insights"] = self._get_all_data_insights()
            
            return await self.python_coder.execute_python_task(**arguments)
        
        elif tool_name == "search_internet":
            return await self.internet_search.search_internet(**arguments)
        
        else:
            return f"❌ 未知工具: {tool_name}"
    
    async def chat(self, message: str) -> str:
        """
        处理用户消息
        
        Args:
            message: 用户输入
            
        Returns:
            助手回复
        """
        # 添加用户消息到历史
        self._history.append({"role": "user", "content": message})
        
        # 检查是否需要压缩历史
        if self.memory_manager.should_compress(self._history):
            compression_result = await self.memory_manager.compress_history(self._history)
            if compression_result["compressed"]:
                # 重建上下文
                self._history = self.memory_manager.build_context_with_memory(compression_result)
        
        # 构建系统提示
        system_prompt = CONTROL_PROMPT
        if self._data_insights:
            system_prompt += "\n\n## 已知数据结构\n"
            for file_name, insights in self._data_insights.items():
                # 只保留摘要信息
                summary = insights[:500] + "..." if len(insights) > 500 else insights
                system_prompt += f"\n### {file_name}\n{summary}\n"
        
        # 创建 prompter 进行 LLM 调用
        prompter = self.create_prompt(system_prompt=system_prompt)
        
        # 使用工具调用模式
        response = await prompter.acall_with_tools(
            messages=self._history,
            tools=self.get_tools(),
            tool_executor=self.execute_tool,
            is_stream=True if self.stream else False,
        )
        
        # 添加助手回复到历史
        self._history.append({"role": "assistant", "content": response})
        
        return response
    
    async def analyze(
        self,
        query: str,
        files: Optional[List[str]] = None,
    ) -> str:
        """
        执行数据分析任务（便捷方法）
        
        Args:
            query: 分析需求
            files: 要分析的文件列表（可选，不传则分析所有文件）
            
        Returns:
            分析结果
        """
        # 如果指定了文件，先查看其结构
        if files:
            for file_name in files:
                if file_name not in self._data_insights:
                    await self.file_viewer.view_file(file_name, purpose="structure")
        
        # 执行分析
        return await self.chat(query)
    
    def _get_all_data_insights(self) -> str:
        """获取所有已知的数据结构信息"""
        if not self._data_insights:
            return "（暂无数据结构信息，请先使用 view_file 查看文件）"
        
        parts = []
        for file_name, insights in self._data_insights.items():
            parts.append(f"=== {file_name} ===\n{insights}")
        
        return "\n\n".join(parts)
    
    def clear_history(self):
        """清空对话历史"""
        self._history = []
    
    def clear_data_insights(self):
        """清空数据结构缓存"""
        self._data_insights = {}
    
    def get_welcome_message(self) -> str:
        """获取欢迎消息"""
        return WELCOME_MESSAGE
