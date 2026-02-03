"""
File Viewer Agent - 通用文件查看智能体

支持查看多种格式的文件：Excel、CSV、Word、PPT、PDF、文本等。

使用示例:
    from alphora_community.agents.file_viewer import FileViewerAgent
    
    agent = FileViewerAgent(base_dir="/path/to/files")
    
    # 预览 Excel
    result = await agent.view_file("data.xlsx")
    
    # 搜索关键词
    result = await agent.view_file("data.xlsx", keyword="北京")
    
    # 查看结构
    result = await agent.view_file("data.xlsx", purpose="structure")
"""

import os
from typing import Optional

from alphora.agent import BaseAgent
from alphora.sandbox import Sandbox

from .viewers.tabular import TabularViewer
from .viewers.document import DocumentViewer
from .viewers.presentation import PresentationViewer
from .viewers.pdf import PDFViewer
from .viewers.text import TextViewer
from .utils.common import find_file, list_available_files, get_file_info


class FileViewerAgent(BaseAgent):
    """
    通用文件查看智能体
    
    为 AI Agent 提供统一的文件查看接口，支持多种文件格式。
    
    Attributes:
        base_dir: 文件基础目录
        sandbox: Sandbox 实例（可选，用于访问沙箱文件）
    """
    
    # 支持的文件扩展名
    TABULAR_EXTENSIONS = TabularViewer.SUPPORTED_EXTENSIONS
    DOCUMENT_EXTENSIONS = DocumentViewer.SUPPORTED_EXTENSIONS
    PRESENTATION_EXTENSIONS = PresentationViewer.SUPPORTED_EXTENSIONS
    PDF_EXTENSIONS = PDFViewer.SUPPORTED_EXTENSIONS
    TEXT_EXTENSIONS = TextViewer.SUPPORTED_EXTENSIONS
    
    def __init__(
        self,
        base_dir: Optional[str] = None,
        sandbox: Optional[Sandbox] = None,
        **kwargs
    ):
        """
        初始化 FileViewerAgent
        
        Args:
            base_dir: 文件基础目录路径
            sandbox: Sandbox 实例（可选，优先使用）
            **kwargs: 传递给 BaseAgent 的参数
        """
        super().__init__(**kwargs)
        self._base_dir: Optional[str] = base_dir
        self._sandbox: Optional[Sandbox] = sandbox

    @property
    def base_dir(self) -> str:
        """获取基础目录"""
        if self._sandbox:
            # 如果有 sandbox，使用其工作目录
            return getattr(self._sandbox, 'workspace_path', None) or self._base_dir
        if self._base_dir:
            return self._base_dir
        raise ValueError("未设置 base_dir 或 sandbox")
    
    def set_base_dir(self, base_dir: str):
        """设置基础目录"""
        self._base_dir = base_dir
        
    def set_sandbox(self, sandbox):
        """设置 Sandbox"""
        self._sandbox = sandbox
    
    async def view_file(
        self,
        file_name: str,
        purpose: str = "preview",
        keyword: Optional[str] = None,
        max_lines: int = 50,
        columns: Optional[str] = None,
        start_row: Optional[int] = None,
        end_row: Optional[int] = None,
        sheet_name: Optional[str] = None,
        page_number: Optional[int] = None,
    ) -> str:
        """
        通用文件查看工具，支持查看各种格式的文件内容。

        【智能推断】
        - 提供 keyword → 自动进入搜索模式
        - 提供 start_row/end_row → 自动进入范围查看模式

        【支持的格式】
        - 表格：Excel (.xlsx/.xls)、CSV、TSV
        - 文档：Word (.docx)、PDF、Markdown、TXT
        - 演示：PowerPoint (.pptx)
        - 数据：JSON、XML、YAML
        - 代码：Python、JavaScript、SQL、HTML 等

        Args:
            file_name: 要查看的文件名（支持模糊匹配）
            purpose: 查看目的
                - "preview": 预览内容（默认）
                - "structure": 查看结构
                - "search": 搜索关键词
                - "range": 查看指定范围
                - "stats": 统计信息（仅表格）
            keyword: 搜索关键词（提供时自动切换 search 模式）
            max_lines: 最大返回行数，默认 50
            columns: [表格] 要查看的列，逗号分隔
            start_row: [表格/文本] 起始行号
            end_row: [表格/文本] 结束行号（负数表示最后N行）
            sheet_name: [Excel] 工作表名称，"__all__" 列出所有
            page_number: [PPT/PDF] 页码

        Returns:
            格式化的文件内容字符串
        """
        # 获取基础目录
        try:
            base = self.base_dir
        except ValueError as e:
            return f"❌ 配置错误: {e}"
        
        # 查找文件
        file_path = find_file(base, file_name)
        if not file_path:
            available = list_available_files(base)
            return f"❌ 找不到文件 '{file_name}'\n\n当前目录下的文件：\n{available}"
        
        # 获取文件扩展名
        ext = os.path.splitext(file_path)[1].lower()
        
        # 根据文件类型分发到对应查看器
        try:
            if ext in self.TABULAR_EXTENSIONS:
                viewer = TabularViewer(file_path)
                return viewer.view(
                    purpose=purpose,
                    keyword=keyword,
                    max_rows=max_lines,
                    columns=columns,
                    start_row=start_row,
                    end_row=end_row,
                    sheet_name=sheet_name
                )
            
            elif ext in self.DOCUMENT_EXTENSIONS:
                viewer = DocumentViewer(file_path)
                return viewer.view(
                    purpose=purpose,
                    keyword=keyword,
                    max_lines=max_lines,
                    page_number=page_number
                )
            
            elif ext in self.PRESENTATION_EXTENSIONS:
                viewer = PresentationViewer(file_path)
                return viewer.view(
                    purpose=purpose,
                    keyword=keyword,
                    max_lines=max_lines,
                    page_number=page_number
                )
            
            elif ext in self.PDF_EXTENSIONS:
                viewer = PDFViewer(file_path)
                return viewer.view(
                    purpose=purpose,
                    keyword=keyword,
                    max_lines=max_lines,
                    page_number=page_number
                )
            
            elif ext in self.TEXT_EXTENSIONS:
                viewer = TextViewer(file_path)
                return viewer.view(
                    purpose=purpose,
                    keyword=keyword,
                    max_lines=max_lines,
                    start_row=start_row,
                    end_row=end_row
                )
            
            else:
                # 尝试作为文本文件处理
                try:
                    viewer = TextViewer(file_path)
                    result = viewer.view(
                        purpose=purpose,
                        keyword=keyword,
                        max_lines=max_lines,
                        start_row=start_row,
                        end_row=end_row
                    )
                    return f"⚠️ 未知文件类型 {ext}，尝试作为文本处理\n\n{result}"
                except Exception:
                    supported = ", ".join(sorted(
                        self.TABULAR_EXTENSIONS |
                        self.DOCUMENT_EXTENSIONS |
                        self.PRESENTATION_EXTENSIONS |
                        self.PDF_EXTENSIONS |
                        self.TEXT_EXTENSIONS
                    ))
                    return f"❌ 不支持的文件类型: {ext}\n\n支持的格式: {supported}"
                    
        except Exception as e:
            return f"❌ 查看文件时出错: {str(e)}"
    
    def list_files(self, max_files: int = 50) -> str:
        """
        列出当前目录下的所有文件
        
        Args:
            max_files: 最大显示文件数
            
        Returns:
            格式化的文件列表
        """
        try:
            base = self.base_dir
        except ValueError as e:
            return f"❌ 配置错误: {e}"
        
        files = list_available_files(base, max_files)
        return f"📁 目录: {base}\n\n{files}"
    
    def get_file_info(self, file_name: str) -> str:
        """
        获取文件的基本信息
        
        Args:
            file_name: 文件名
            
        Returns:
            文件信息字符串
        """
        try:
            base = self.base_dir
        except ValueError as e:
            return f"❌ 配置错误: {e}"
        
        file_path = find_file(base, file_name)
        if not file_path:
            return f"❌ 找不到文件 '{file_name}'"
        
        info = get_file_info(file_path)
        
        lines = [
            f"📄 文件名: {info['name']}",
            f"📁 路径: {info['path']}",
            f"📦 大小: {info['size_human']}",
            f"🕐 修改时间: {info['modified_str']}",
            f"📋 类型: {info['extension']}",
        ]
        
        return '\n'.join(lines)
