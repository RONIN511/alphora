"""
PDF 文件查看器 - 处理 .pdf 文件
"""
from typing import Optional, List, Tuple

from ..utils.common import get_file_info


class PDFViewer:
    """PDF 文件查看器"""
    
    SUPPORTED_EXTENSIONS = {'.pdf'}
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.file_info = get_file_info(file_path)
        self.ext = self.file_info['extension']
        
    def view(
        self,
        purpose: str = "preview",
        keyword: Optional[str] = None,
        max_lines: int = 100,
        page_number: Optional[int] = None,
    ) -> str:
        """查看 PDF 内容"""
        purpose, warnings = self._infer_params(purpose, keyword)
        
        # 尝试使用 PyMuPDF
        try:
            import fitz
            return self._view_with_pymupdf(purpose, keyword, max_lines, page_number, warnings)
        except ImportError:
            pass
        
        # 尝试使用 pdfplumber
        try:
            import pdfplumber
            return self._view_with_pdfplumber(purpose, keyword, max_lines, page_number, warnings)
        except ImportError:
            return "❌ 需要安装 PDF 库: pip install pymupdf 或 pip install pdfplumber"
    
    def _infer_params(self, purpose: str, keyword: Optional[str]) -> Tuple[str, List[str]]:
        warnings = []
        if keyword and purpose != "search":
            warnings.append(f"⚠️ 检测到 keyword，已切换为 search 模式")
            purpose = "search"
        if purpose == "search" and not keyword:
            purpose = "preview"
        return purpose, warnings
    
    def _format_header(self, total_pages: int, warnings: List[str]) -> str:
        lines = [
            f"📕 文件: {self.file_info['name']}",
            f"📦 大小: {self.file_info['size_human']}",
            f"📋 页数: {total_pages}",
        ]
        if warnings:
            lines.extend([""] + warnings)
        return '\n'.join(lines)
    
    def _view_with_pymupdf(self, purpose, keyword, max_lines, page_number, warnings) -> str:
        import fitz
        
        try:
            doc = fitz.open(self.file_path)
        except Exception as e:
            return f"❌ 无法打开 PDF: {e}"
        
        total_pages = len(doc)
        
        try:
            if purpose == "structure":
                return self._get_structure_pymupdf(doc, total_pages, warnings)
            elif purpose == "search":
                return self._search_pymupdf(doc, keyword, max_lines, warnings)
            elif page_number is not None:
                return self._view_page_pymupdf(doc, page_number, total_pages, warnings)
            else:
                return self._preview_pymupdf(doc, total_pages, max_lines, warnings)
        finally:
            doc.close()
    
    def _get_structure_pymupdf(self, doc, total_pages, warnings) -> str:
        lines = [self._format_header(total_pages, warnings), ""]
        
        toc = doc.get_toc()
        if toc:
            lines.append("【目录结构】")
            for level, title, page in toc[:30]:
                indent = "  " * (level - 1)
                lines.append(f"{indent}• {title} (第{page}页)")
        else:
            lines.append("【各页概览】")
            for i in range(min(10, total_pages)):
                page = doc[i]
                text = page.get_text()
                first_line = text.split('\n')[0].strip()[:50] if text.strip() else "(无文本)"
                lines.append(f"  第{i+1}页: {first_line}...")
        
        return '\n'.join(lines)
    
    def _preview_pymupdf(self, doc, total_pages, max_lines, warnings) -> str:
        lines = [self._format_header(total_pages, warnings), "", "【内容预览】"]
        
        char_count = 0
        max_chars = 4000
        
        for i, page in enumerate(doc):
            if char_count > max_chars:
                break
            text = page.get_text().strip()
            if text:
                lines.append(f"\n━━━ 第{i+1}页 ━━━")
                page_text = text[:1500] if len(text) > 1500 else text
                lines.append(page_text)
                char_count += len(page_text)
        
        return '\n'.join(lines)
    
    def _view_page_pymupdf(self, doc, page_number, total_pages, warnings) -> str:
        if page_number < 1 or page_number > total_pages:
            return f"❌ 页码超出范围 (1-{total_pages})"
        
        page = doc[page_number - 1]
        text = page.get_text()
        
        lines = [
            f"📕 文件: {self.file_info['name']}",
            f"📋 第 {page_number}/{total_pages} 页", "",
            "【页面内容】",
            text[:5000] if text.strip() else "(此页没有可提取的文本)"
        ]
        
        return '\n'.join(lines)
    
    def _search_pymupdf(self, doc, keyword, max_lines, warnings) -> str:
        results = []
        keyword_lower = keyword.lower()
        
        for i, page in enumerate(doc, 1):
            text = page.get_text()
            if keyword_lower in text.lower():
                idx = text.lower().find(keyword_lower)
                start = max(0, idx - 50)
                end = min(len(text), idx + len(keyword) + 80)
                context = text[start:end].replace('\n', ' ')
                results.append({'page': i, 'content': context})
        
        lines = [
            self._format_header(len(doc), warnings), "",
            f"🔍 搜索: '{keyword}'",
            f"📋 找到 {len(results)} 页匹配", ""
        ]
        
        if results:
            for r in results[:max_lines]:
                lines.append(f"[第{r['page']}页] ...{r['content']}...")
        else:
            lines.append(f"未找到包含 '{keyword}' 的内容")
        
        return '\n'.join(lines)
    
    def _view_with_pdfplumber(self, purpose, keyword, max_lines, page_number, warnings) -> str:
        import pdfplumber
        
        try:
            with pdfplumber.open(self.file_path) as pdf:
                total_pages = len(pdf.pages)
                
                if purpose == "structure":
                    lines = [self._format_header(total_pages, warnings), "", "【各页概览】"]
                    for i, page in enumerate(pdf.pages[:10], 1):
                        text = page.extract_text() or ""
                        first_line = text.split('\n')[0].strip()[:50] if text.strip() else "(无文本)"
                        lines.append(f"  第{i}页: {first_line}...")
                    return '\n'.join(lines)
                
                elif purpose == "search":
                    results = []
                    keyword_lower = keyword.lower()
                    for i, page in enumerate(pdf.pages, 1):
                        text = page.extract_text() or ""
                        if keyword_lower in text.lower():
                            results.append({'page': i, 'content': text[:100]})
                    
                    lines = [self._format_header(total_pages, warnings), "", f"🔍 搜索: '{keyword}'", f"📋 找到 {len(results)} 页", ""]
                    for r in results[:max_lines]:
                        lines.append(f"[第{r['page']}页] {r['content']}")
                    return '\n'.join(lines)
                
                elif page_number is not None:
                    if page_number < 1 or page_number > total_pages:
                        return f"❌ 页码超出范围 (1-{total_pages})"
                    page = pdf.pages[page_number - 1]
                    text = page.extract_text() or "(无法提取文本)"
                    return f"📕 第 {page_number}/{total_pages} 页\n\n{text[:5000]}"
                
                else:  # preview
                    lines = [self._format_header(total_pages, warnings), "", "【内容预览】"]
                    for i, page in enumerate(pdf.pages[:5], 1):
                        text = page.extract_text()
                        if text:
                            lines.append(f"\n━━━ 第{i}页 ━━━")
                            lines.append(text[:1500])
                    return '\n'.join(lines)
                    
        except Exception as e:
            return f"❌ 无法打开 PDF: {e}"
