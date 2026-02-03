"""
File Viewer Agent - 通用文件查看智能体

支持查看多种格式的文件：Excel、CSV、Word、PPT、PDF、文本等。

快速开始:
    from alphora_community.agents.file_viewer import FileViewerAgent
    
    agent = FileViewerAgent(base_dir="/path/to/files")
    
    # 预览 Excel
    result = await agent.view_file("data.xlsx")
    
    # 搜索关键词（自动推断模式）
    result = await agent.view_file("data.xlsx", keyword="北京")
    
    # 查看结构
    result = await agent.view_file("data.xlsx", purpose="structure")

支持的格式:
- 表格：.xlsx, .xls, .csv, .tsv
- 文档：.docx, .doc
- 演示：.pptx, .ppt
- PDF：.pdf
- 文本：.txt, .md, .json, .xml, .yaml, .py, .js 等
"""

__version__ = "1.0.0"

from .agent import FileViewerAgent
from .viewers import (
    TabularViewer,
    DocumentViewer,
    PresentationViewer,
    PDFViewer,
    TextViewer,
)
from .utils import (
    find_file,
    list_available_files,
    get_file_info,
    format_file_size,
    clean_text,
    truncate_text,
)

__all__ = [
    # 主类
    'FileViewerAgent',
    
    # 查看器
    'TabularViewer',
    'DocumentViewer',
    'PresentationViewer',
    'PDFViewer',
    'TextViewer',
    
    # 工具函数
    'find_file',
    'list_available_files',
    'get_file_info',
    'format_file_size',
    'clean_text',
    'truncate_text',
]
