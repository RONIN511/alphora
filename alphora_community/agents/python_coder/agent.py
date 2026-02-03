"""
Python Coder Agent - 代码生成与执行智能体

基于 Alphora Sandbox 组件提供的 Python 代码生成、执行、自动修复能力。

使用示例:
    from alphora.sandbox import Sandbox
    from alphora_community.agents.python_coder import PythonCoderAgent
    
    async with Sandbox.create_local() as sandbox:
        agent = PythonCoderAgent(sandbox=sandbox)
        
        result = await agent.execute_code_step(
            description="计算数据统计",
            code="import pandas as pd; print(pd.read_excel('data.xlsx').describe())"
        )
"""

import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from alphora.agent import BaseAgent

from .prompts import (
    CODER_SYSTEM_PROMPT,
    CODER_TASK_TEMPLATE,
    FIXER_SYSTEM_PROMPT,
    FIXER_TASK_TEMPLATE,
    ANALYZER_SYSTEM_PROMPT,
    SUMMARY_TASK_TEMPLATE,
)
from .utils import (
    extract_code_block,
    detect_missing_packages,
    format_error_context,
    parse_traceback,
    suggest_fixes,
)


@dataclass
class CodeExecutionResult:
    """代码执行结果"""
    success: bool
    stdout: str = ""
    stderr: str = ""
    execution_time: float = 0.0
    generated_files: List[str] = None
    
    def __post_init__(self):
        if self.generated_files is None:
            self.generated_files = []


class PythonCoderAgent(BaseAgent):
    """
    Python 代码生成与执行智能体
    
    核心能力：
    1. execute_code_step - 执行单步代码（推荐用于 Agent 工具调用）
    2. execute_python_task - 完整任务流程（生成→执行→修复→总结）
    3. generate_code - 根据需求生成代码
    4. fix_code - 修复执行失败的代码
    
    Attributes:
        sandbox: Alphora Sandbox 实例
        auto_install: 是否自动安装缺失的包
        max_fix_attempts: 最大代码修复尝试次数
    """
    
    def __init__(
        self,
        sandbox=None,
        auto_install: bool = True,
        max_fix_attempts: int = 3,
        **kwargs
    ):
        """
        初始化 Python Coder Agent
        
        Args:
            sandbox: Alphora Sandbox 实例
            auto_install: 是否自动安装缺失的包
            max_fix_attempts: 最大代码修复尝试次数
            **kwargs: 传递给 BaseAgent 的参数
        """
        super().__init__(**kwargs)
        self._sandbox = sandbox
        self.auto_install = auto_install
        self.max_fix_attempts = max_fix_attempts
    
    @property
    def sandbox(self):
        """获取 Sandbox 实例"""
        if self._sandbox is None:
            raise ValueError("Sandbox 未设置，请先调用 set_sandbox() 或在初始化时传入")
        return self._sandbox
    
    def set_sandbox(self, sandbox):
        """设置 Sandbox 实例"""
        self._sandbox = sandbox
    
    async def execute_code_step(
        self,
        description: str,
        code: str
    ) -> str:
        """
        执行单步 Python 代码片段，用于迭代式数据探索和处理。

        【使用场景】
        - 分步探索数据：先看数据结构，再决定下一步
        - 验证处理思路：测试某个想法是否可行
        - 复杂任务拆解：把大任务分成多个小步骤逐一执行

        【重要特性】
        - 每次执行都是独立环境，变量不会保留到下次
        - 每次都需要重新 import 依赖库和读取文件
        - 不会自动修复错误，你需要根据报错自行调整

        【文件系统】
        代码在沙箱环境中执行，可自由读写当前目录下的文件：
        - 读取用户上传的文件
        - 保存处理后的数据、图表、报告等
        - 创建临时文件供后续步骤使用

        【matplotlib 中文支持】
        如果涉及画图，需要设置中文字体：
        ```python
        import matplotlib.pyplot as plt
        plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        ```

        Args:
            description: 本步骤的目的说明（如"查看数据结构"、"按城市分组统计"）
            code: 要执行的 Python 代码

        Returns:
            执行结果（stdout 或 stderr）
        """
        # 输出描述
        if self.stream:
            await self.stream.astream_message(content=f"{description}\n\n", interval=0.01)
            await self.stream.astream_message(content_type='m_python', content=code)
        
        # 执行代码
        result = await self.sandbox.execute_code(code)
        
        if result.success:
            output = result.stdout or "(执行成功，无输出)"
            
            # 检查生成的文件
            try:
                files = await self.sandbox.list_files()
                if files:
                    file_names = [f.name for f in files]
                    output += f"\n\n📁 当前目录文件: {file_names}"
            except Exception:
                pass
            
            return output
        else:
            error_msg = result.stderr or result.error or "未知错误"
            return f"❌ 执行出错:\n{error_msg}"
    
    async def execute_python_task(
        self,
        thought: str,
        query: str,
        data_insights: str,
        additional_context: Optional[str] = None,
    ) -> str:
        """
        根据需求自动生成并执行完整的 Python 代码。

        完整流程：分析需求 → 生成代码 → 安装依赖 → 执行代码 → 自动修复 → 总结结果

        【适用场景】
        - 任务目标明确，一次性可完成
        - 已通过 view_file 充分了解数据结构
        - 不需要边做边观察中间结果

        【自动化能力】
        - 自动修复：代码执行失败时自动分析错误并修复（最多3次）
        - 自动安装：检测到缺失的 Python 包时自动 pip install

        Args:
            thought: 解题思路和实现策略
            query: 用户的原始任务需求
            data_insights: 数据结构信息（文件名、列名、数据类型等）
            additional_context: 补充信息或特殊要求

        Returns:
            任务执行结果的总结
        """
        # 输出解题思路
        if self.stream:
            await self.stream.astream_message(content=thought, interval=0.01)
            await self.stream.astream_message(content='\n\n', interval=0.01)
        
        # 获取文件列表
        try:
            files = await self._get_files_list()
        except Exception as e:
            return f"❌ 获取文件列表失败: {str(e)}"
        
        # 生成代码
        if self.stream:
            await self.stream.astream_message(content='正在生成代码...\n', interval=0.01)
        
        code = await self._generate_code(
            query=query,
            files=files,
            data_insights=data_insights,
            additional_context=additional_context,
        )
        
        if not code:
            return "❌ 代码生成失败，未能提取有效的 Python 代码"
        
        # 检测并安装缺失的包
        if self.auto_install:
            await self._ensure_dependencies(code)
        
        # 执行代码（带自动修复）
        result = await self._execute_with_recovery(
            code=code,
            query=query,
            data_insights=data_insights,
            files=files,
        )
        
        # 处理执行结果
        if result.success:
            # 生成总结
            summary = await self._summarize_result(
                task=query,
                stdout=result.stdout,
                generated_files=result.generated_files,
            )
            return summary
        else:
            error_msg = f"""
❌ 代码执行失败

**错误信息:**
```
{result.stderr[:1500]}
```

**建议:**
- 检查数据格式是否与预期一致
- 简化处理需求，分步完成
- 提供更详细的数据结构信息
"""
            if self.stream:
                await self.stream.astream_message(content=error_msg, interval=0.01)
            return error_msg
    
    async def generate_code(
        self,
        query: str,
        data_insights: str,
        files: Optional[List[str]] = None,
        additional_context: Optional[str] = None,
    ) -> Optional[str]:
        """
        根据需求生成 Python 代码（不执行）
        
        Args:
            query: 用户需求
            data_insights: 数据结构信息
            files: 可用文件列表
            additional_context: 补充信息
            
        Returns:
            生成的代码字符串，失败返回 None
        """
        if files is None:
            files = await self._get_files_list()
        
        return await self._generate_code(
            query=query,
            files=files,
            data_insights=data_insights,
            additional_context=additional_context,
        )
    
    async def fix_code(
        self,
        code: str,
        error_info: str,
        query: str,
        data_insights: str,
    ) -> Optional[str]:
        """
        修复执行失败的代码
        
        Args:
            code: 出错的代码
            error_info: 错误信息
            query: 原始需求
            data_insights: 数据结构信息
            
        Returns:
            修复后的代码，失败返回 None
        """
        files = await self._get_files_list()
        
        return await self._fix_code(
            code=code,
            error_info=error_info,
            query=query,
            data_insights=data_insights,
            files=files,
        )
    
    # ==================== 私有方法 ====================
    
    async def _get_files_list(self) -> List[str]:
        """获取沙箱中的文件列表"""
        try:
            files = await self.sandbox.list_files()
            return [f.name for f in files]
        except Exception:
            return []
    
    async def _generate_code(
        self,
        query: str,
        files: List[str],
        data_insights: str,
        additional_context: Optional[str] = None,
    ) -> Optional[str]:
        """生成 Python 代码"""
        from jinja2 import Template
        
        task_template = Template(CODER_TASK_TEMPLATE)
        task_content = task_template.render(
            query=query,
            files=files,
            data_insights=data_insights,
            additional_context=additional_context,
        )
        
        prompter = self.create_prompt(system_prompt=CODER_SYSTEM_PROMPT)
        
        response = await prompter.acall(
            query=task_content,
            is_stream=True if self.stream else False,
            content_type='m_python' if self.stream else None,
            return_generator=False,
        )
        
        if self.stream:
            await self.stream.astream_message(content='\n')
        
        return extract_code_block(response)
    
    async def _ensure_dependencies(self, code: str) -> List[str]:
        """确保代码依赖的包已安装"""
        missing = detect_missing_packages(code)
        
        if not missing:
            return []
        
        installed = []
        for package in missing:
            try:
                result = await self.sandbox.install_package(package)
                if result.success:
                    installed.append(package)
                    if self.stream:
                        await self.stream.astream_message(
                            content=f"📦 已安装: {package}\n",
                            interval=0.01
                        )
            except Exception as e:
                if self.stream:
                    await self.stream.astream_message(
                        content=f"⚠️ 安装 {package} 失败: {e}\n",
                        interval=0.01
                    )
        
        return installed
    
    async def _execute_with_recovery(
        self,
        code: str,
        query: str,
        data_insights: str,
        files: List[str],
    ) -> CodeExecutionResult:
        """执行代码，失败时自动修复"""
        current_code = code
        
        for attempt in range(self.max_fix_attempts):
            # 执行代码
            result = await self.sandbox.execute_code(current_code)
            
            if result.success:
                # 输出执行结果
                if self.stream and result.stdout:
                    await self.stream.astream_message(
                        content=result.stdout,
                        content_type='stdout'
                    )
                
                # 获取生成的文件
                generated_files = []
                try:
                    files_after = await self.sandbox.list_files()
                    generated_files = [f.name for f in files_after]
                except Exception:
                    pass
                
                return CodeExecutionResult(
                    success=True,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    execution_time=result.execution_time,
                    generated_files=generated_files,
                )
            
            # 执行失败
            error_info = result.stderr or result.error or "未知错误"
            
            # 检查是否是包缺失
            missing_pkg = self._detect_missing_from_error(error_info)
            if missing_pkg:
                try:
                    pkg_result = await self.sandbox.install_package(missing_pkg)
                    if pkg_result.success:
                        if self.stream:
                            await self.stream.astream_message(
                                content=f"📦 已安装缺失的包: {missing_pkg}\n",
                                interval=0.01
                            )
                        continue  # 重新执行，不计入修复次数
                except Exception:
                    pass
            
            # 最后一次尝试，不再修复
            if attempt >= self.max_fix_attempts - 1:
                break
            
            # 使用 LLM 修复
            if self.stream:
                await self.stream.astream_message(
                    content=f"\n⚠️ 执行出错 (第 {attempt + 1}/{self.max_fix_attempts} 次)，正在修复...\n",
                    interval=0.01
                )
            
            fixed_code = await self._fix_code(
                code=current_code,
                error_info=error_info,
                query=query,
                data_insights=data_insights,
                files=files,
            )
            
            if fixed_code:
                current_code = fixed_code
            else:
                break
        
        # 所有尝试都失败
        return CodeExecutionResult(
            success=False,
            stdout=result.stdout if result else "",
            stderr=result.stderr if result else "未知错误",
        )
    
    async def _fix_code(
        self,
        code: str,
        error_info: str,
        query: str,
        data_insights: str,
        files: List[str],
    ) -> Optional[str]:
        """使用 LLM 修复代码"""
        from jinja2 import Template
        
        # 解析错误信息
        error_analysis = parse_traceback(error_info)
        suggestions = suggest_fixes(
            error_analysis.get('error_type', ''),
            error_analysis.get('error_message', '')
        )
        error_analysis['suggestions'] = suggestions
        
        # 格式化错误上下文
        error_context = format_error_context(
            code,
            error_info,
            error_analysis.get('error_line')
        )
        
        # 构建修复提示
        task_template = Template(FIXER_TASK_TEMPLATE)
        task_content = task_template.render(
            query=query,
            files=files,
            data_insights=data_insights,
            wrong_code=code,
            error_info=error_context,
            error_analysis=error_analysis if error_analysis.get('error_type') else None,
        )
        
        try:
            prompter = self.create_prompt(system_prompt=FIXER_SYSTEM_PROMPT)
            
            response = await prompter.acall(
                query=task_content,
                is_stream=True if self.stream else False,
                content_type='m_python' if self.stream else None,
                return_generator=False,
            )
            
            return extract_code_block(response)
        except Exception:
            return None
    
    async def _summarize_result(
        self,
        task: str,
        stdout: str,
        generated_files: List[str],
    ) -> str:
        """总结执行结果"""
        from jinja2 import Template
        
        summary_template = Template(SUMMARY_TASK_TEMPLATE)
        task_content = summary_template.render(
            task=task,
            stdout=stdout,
            generated_files=generated_files if generated_files else None,
        )
        
        prompter = self.create_prompt(system_prompt=ANALYZER_SYSTEM_PROMPT)
        
        summary = await prompter.acall(
            query=task_content,
            is_stream=True if self.stream else False,
        )
        
        return summary
    
    def _detect_missing_from_error(self, error_message: str) -> Optional[str]:
        """从错误信息中检测缺失的包"""
        # 常见第三方包映射
        package_mapping = {
            'pandas': 'pandas',
            'numpy': 'numpy',
            'matplotlib': 'matplotlib',
            'seaborn': 'seaborn',
            'openpyxl': 'openpyxl',
            'xlrd': 'xlrd',
            'requests': 'requests',
            'bs4': 'beautifulsoup4',
            'PIL': 'Pillow',
            'sklearn': 'scikit-learn',
            'cv2': 'opencv-python',
            'yaml': 'pyyaml',
            'docx': 'python-docx',
            'pptx': 'python-pptx',
            'fitz': 'pymupdf',
        }
        
        # ModuleNotFoundError: No module named 'xxx'
        match = re.search(r"No module named ['\"](\w+)['\"]", error_message)
        if match:
            module_name = match.group(1)
            return package_mapping.get(module_name, module_name)
        
        return None
