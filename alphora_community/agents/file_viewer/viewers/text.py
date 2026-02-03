"""
文本文件查看器 - 处理 txt/md/json/xml/yaml/代码等文件
"""
import os
import json
from typing import Optional, List, Dict, Any, Tuple

from ..utils.common import get_file_info, truncate_text


class TextViewer:
    """文本文件查看器"""
    
    SUPPORTED_EXTENSIONS = {
        '.txt', '.md', '.markdown',
        '.json', '.xml', '.yaml', '.yml',
        '.log', '.ini', '.cfg', '.conf',
        '.py', '.js', '.ts', '.html', '.css', '.sql',
        '.java', '.c', '.cpp', '.h', '.go', '.rs',
        '.sh', '.bash', '.zsh',
        '.env', '.gitignore', '.dockerfile'
    }
    
    CODE_EXTENSIONS = {
        '.py', '.js', '.ts', '.html', '.css', '.sql',
        '.java', '.c', '.cpp', '.h', '.go', '.rs',
        '.sh', '.bash', '.zsh'
    }
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.file_info = get_file_info(file_path)
        self.ext = self.file_info['extension']
        
    def view(
        self,
        purpose: str = "preview",
        keyword: Optional[str] = None,
        max_lines: int = 100,
        start_row: Optional[int] = None,
        end_row: Optional[int] = None,
    ) -> str:
        """查看文本文件内容"""
        purpose, warnings = self._infer_and_validate_params(purpose, keyword, start_row, end_row)
        
        content, error = self._read_file()
        if error:
            return error
        
        lines = content.split('\n')
        total_lines = len(lines)
        
        if self.ext == '.json' and purpose == "structure":
            return self._get_json_structure(content, warnings)
        
        if purpose == "structure":
            return self._get_structure(lines, total_lines, warnings)
        elif purpose == "search":
            return self._search(lines, keyword, max_lines, warnings)
        elif purpose == "range":
            return self._get_range(lines, total_lines, start_row, end_row, max_lines, warnings)
        else:
            return self._preview(lines, total_lines, max_lines, warnings)
    
    def _infer_and_validate_params(self, purpose, keyword, start_row, end_row) -> Tuple[str, List[str]]:
        warnings = []
        if keyword and purpose != "search":
            warnings.append(f"⚠️ 检测到 keyword='{keyword}'，已自动切换为 search 模式")
            purpose = "search"
        if (start_row is not None or end_row is not None) and purpose not in ("search", "range"):
            purpose = "range"
        if purpose == "search" and not keyword:
            purpose = "preview"
        return purpose, warnings
    
    def _read_file(self) -> Tuple[str, Optional[str]]:
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
        for encoding in encodings:
            try:
                with open(self.file_path, 'r', encoding=encoding) as f:
                    return f.read(), None
            except UnicodeDecodeError:
                continue
            except Exception as e:
                return "", f"❌ 读取文件失败: {e}"
        return "", "❌ 无法识别文件编码"
    
    def _format_header(self, total_lines: int, warnings: List[str]) -> str:
        icon = "📝" if self.ext in self.CODE_EXTENSIONS else "📄"
        lines = [
            f"{icon} 文件: {self.file_info['name']}",
            f"📦 大小: {self.file_info['size_human']}",
            f"📋 行数: {total_lines}",
        ]
        if warnings:
            lines.extend([""] + warnings)
        return '\n'.join(lines)
    
    def _get_structure(self, lines: List[str], total_lines: int, warnings: List[str]) -> str:
        output = [self._format_header(total_lines, warnings), ""]
        non_empty_lines = sum(1 for line in lines if line.strip())
        output.append(f"【文件统计】\n  总行数: {total_lines}\n  非空行: {non_empty_lines}")
        return '\n'.join(output)
    
    def _preview(self, lines: List[str], total_lines: int, max_lines: int, warnings: List[str]) -> str:
        output = [self._format_header(total_lines, warnings), "", "【内容预览】", ""]
        for i, line in enumerate(lines[:max_lines], 1):
            output.append(f"{i:4d} | {line}")
        if total_lines > max_lines:
            output.append(f"\n... 还有 {total_lines - max_lines} 行未显示")
        return '\n'.join(output)
    
    def _search(self, lines: List[str], keyword: str, max_lines: int, warnings: List[str]) -> str:
        results = []
        keyword_lower = keyword.lower()
        for i, line in enumerate(lines, 1):
            if keyword_lower in line.lower():
                results.append((i, line))
        
        output = [
            self._format_header(len(lines), warnings), "",
            f"🔍 搜索: '{keyword}'",
            f"📋 找到 {len(results)} 行匹配", ""
        ]
        
        if not results:
            output.append(f"未找到包含 '{keyword}' 的内容")
        else:
            for line_no, line in results[:max_lines]:
                display_line = line[:150] + "..." if len(line) > 150 else line
                output.append(f"{line_no:4d} | {display_line}")
        
        return '\n'.join(output)
    
    def _get_range(self, lines: List[str], total_lines: int, start_row, end_row, max_lines, warnings) -> str:
        if end_row is not None and end_row < 0:
            display_lines = lines[end_row:]
            actual_start = total_lines + end_row + 1
        elif start_row is not None:
            start_idx = max(0, start_row - 1)
            end_idx = min(total_lines, end_row) if end_row else min(total_lines, start_idx + max_lines)
            display_lines = lines[start_idx:end_idx]
            actual_start = start_row
        else:
            display_lines = lines[:max_lines]
            actual_start = 1
        
        output = [self._format_header(total_lines, warnings), ""]
        for i, line in enumerate(display_lines, actual_start):
            output.append(f"{i:4d} | {line}")
        return '\n'.join(output)
    
    def _get_json_structure(self, content: str, warnings: List[str]) -> str:
        output = [self._format_header(content.count('\n') + 1, warnings), ""]
        try:
            data = json.loads(content)
            output.append("【JSON 结构】")
            output.extend(self._analyze_json_structure(data, "", 0))
        except json.JSONDecodeError as e:
            output.append(f"❌ JSON 解析错误: {e}")
        return '\n'.join(output)
    
    def _analyze_json_structure(self, obj: Any, prefix: str = "", depth: int = 0) -> List[str]:
        if depth > 4:
            return [f"{'  ' * depth}{prefix}..."]
        
        result = []
        indent = "  " * depth
        
        if isinstance(obj, dict):
            result.append(f"{indent}{prefix}对象 ({len(obj)} 个字段)")
            for key, value in list(obj.items())[:10]:
                result.extend(self._analyze_json_structure(value, f"{key}: ", depth + 1))
        elif isinstance(obj, list):
            result.append(f"{indent}{prefix}数组 ({len(obj)} 个元素)")
            if obj:
                result.extend(self._analyze_json_structure(obj[0], "[0]: ", depth + 1))
        else:
            type_name = type(obj).__name__
            value_preview = str(obj)[:50]
            result.append(f"{indent}{prefix}{type_name} = {value_preview}")
        
        return result
