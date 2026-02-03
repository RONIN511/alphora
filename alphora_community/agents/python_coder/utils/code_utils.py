"""
代码处理工具函数
"""
import re
import hashlib
from typing import Optional, List, Dict, Set


def extract_code_block(text: str, language: str = "python") -> Optional[str]:
    """
    从文本中提取代码块
    
    支持多种格式：
    1. ```python ... ```
    2. ```py ... ```
    3. ``` ... ```（无语言标记）
    
    Args:
        text: 包含代码块的文本
        language: 目标语言（默认 python）
        
    Returns:
        提取的代码字符串，未找到返回 None
    """
    if not text:
        return None
    
    # 尝试带语言标记的代码块
    patterns = [
        rf'```{language}\s*([\s\S]*?)\s*```',
        r'```py\s*([\s\S]*?)\s*```',
        r'```\s*([\s\S]*?)\s*```',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            code = match.group(1).strip()
            if code:
                return code
    
    # 如果没有代码块标记，检查是否整段都是代码
    if _looks_like_python_code(text):
        return text.strip()
    
    return None


def _looks_like_python_code(text: str) -> bool:
    """检查文本是否看起来像 Python 代码"""
    indicators = [
        'import ', 'from ', 'def ', 'class ',
        'if __name__', 'print(', 'return ',
        '= pd.', '= np.', '.read_csv', '.read_excel'
    ]
    return any(indicator in text for indicator in indicators)


def extract_imports(code: str) -> List[str]:
    """
    从代码中提取所有 import 语句
    
    Args:
        code: Python 代码字符串
        
    Returns:
        import 语句列表
    """
    imports = []
    
    # 正则匹配 import 语句
    import_patterns = [
        r'^import\s+[\w\s,\.]+',
        r'^from\s+[\w\.]+\s+import\s+[\w\s,\*]+',
    ]
    
    for line in code.split('\n'):
        line = line.strip()
        for pattern in import_patterns:
            if re.match(pattern, line):
                imports.append(line)
                break
    
    return imports


def detect_missing_packages(code: str) -> Set[str]:
    """
    检测代码中可能缺失的第三方包
    
    Args:
        code: Python 代码字符串
        
    Returns:
        可能需要安装的包名集合
    """
    # 标准库模块（部分常用）
    stdlib_modules = {
        'os', 'sys', 're', 'json', 'csv', 'datetime', 'time', 'math',
        'random', 'collections', 'itertools', 'functools', 'typing',
        'pathlib', 'io', 'shutil', 'tempfile', 'subprocess', 'threading',
        'multiprocessing', 'logging', 'unittest', 'argparse', 'copy',
        'pickle', 'hashlib', 'base64', 'urllib', 'http', 'html', 'xml',
        'sqlite3', 'statistics', 'decimal', 'fractions', 'operator',
        'string', 'textwrap', 'struct', 'codecs', 'unicodedata',
        'calendar', 'locale', 'gettext', 'bisect', 'heapq', 'array',
        'weakref', 'types', 'contextlib', 'abc', 'dataclasses', 'enum',
        'graphlib', 'pprint', 'reprlib', 'numbers', 'cmath', 'queue',
        'asyncio', 'concurrent', 'socket', 'ssl', 'select', 'selectors',
        'email', 'mimetypes', 'binhex', 'binascii', 'quopri', 'uu',
        'gzip', 'bz2', 'lzma', 'zipfile', 'tarfile', 'zlib',
        'configparser', 'tomllib', 'netrc', 'plistlib', 'secrets',
        'hmac', 'fileinput', 'stat', 'filecmp', 'glob', 'fnmatch',
        'linecache', 'traceback', 'gc', 'inspect', 'dis', 'tracemalloc',
        'importlib', 'zipimport', 'pkgutil', 'modulefinder', 'runpy',
        'warnings', 'atexit', 'builtins', 'uuid', 'ast',
    }
    
    # 常见第三方包及其 import 名称映射
    package_mapping = {
        'pandas': 'pandas',
        'pd': 'pandas',
        'numpy': 'numpy',
        'np': 'numpy',
        'matplotlib': 'matplotlib',
        'plt': 'matplotlib',
        'seaborn': 'seaborn',
        'sns': 'seaborn',
        'sklearn': 'scikit-learn',
        'scipy': 'scipy',
        'requests': 'requests',
        'bs4': 'beautifulsoup4',
        'BeautifulSoup': 'beautifulsoup4',
        'PIL': 'Pillow',
        'cv2': 'opencv-python',
        'torch': 'torch',
        'tensorflow': 'tensorflow',
        'tf': 'tensorflow',
        'keras': 'keras',
        'flask': 'flask',
        'django': 'django',
        'fastapi': 'fastapi',
        'sqlalchemy': 'sqlalchemy',
        'openpyxl': 'openpyxl',
        'xlrd': 'xlrd',
        'xlwt': 'xlwt',
        'xlsxwriter': 'xlsxwriter',
        'docx': 'python-docx',
        'pptx': 'python-pptx',
        'PyPDF2': 'PyPDF2',
        'fitz': 'pymupdf',
        'pdfplumber': 'pdfplumber',
        'yaml': 'pyyaml',
        'toml': 'toml',
        'dotenv': 'python-dotenv',
        'tqdm': 'tqdm',
        'rich': 'rich',
        'click': 'click',
        'typer': 'typer',
        'httpx': 'httpx',
        'aiohttp': 'aiohttp',
        'redis': 'redis',
        'pymongo': 'pymongo',
        'psycopg2': 'psycopg2-binary',
        'mysql': 'mysql-connector-python',
        'pymysql': 'pymysql',
        'boto3': 'boto3',
        'paramiko': 'paramiko',
        'cryptography': 'cryptography',
        'jwt': 'pyjwt',
        'arrow': 'arrow',
        'pendulum': 'pendulum',
        'dateutil': 'python-dateutil',
        'pytz': 'pytz',
        'chardet': 'chardet',
        'colorama': 'colorama',
        'tabulate': 'tabulate',
        'prettytable': 'prettytable',
        'jinja2': 'jinja2',
        'Jinja2': 'jinja2',
        'lxml': 'lxml',
        'html5lib': 'html5lib',
        'cssselect': 'cssselect',
        'parsel': 'parsel',
        'scrapy': 'scrapy',
        'playwright': 'playwright',
        'selenium': 'selenium',
        'pytest': 'pytest',
        'coverage': 'coverage',
        'faker': 'faker',
        'networkx': 'networkx',
        'sympy': 'sympy',
        'statsmodels': 'statsmodels',
        'xgboost': 'xgboost',
        'lightgbm': 'lightgbm',
        'catboost': 'catboost',
        'transformers': 'transformers',
        'datasets': 'datasets',
        'spacy': 'spacy',
        'nltk': 'nltk',
        'gensim': 'gensim',
        'jieba': 'jieba',
        'wordcloud': 'wordcloud',
        'plotly': 'plotly',
        'bokeh': 'bokeh',
        'altair': 'altair',
        'streamlit': 'streamlit',
        'gradio': 'gradio',
        'dash': 'dash',
    }
    
    missing_packages = set()
    
    # 提取所有 import 的模块名
    import_pattern = r'(?:from|import)\s+([\w\.]+)'
    
    for match in re.finditer(import_pattern, code):
        module_name = match.group(1).split('.')[0]  # 取顶层模块名
        
        # 跳过标准库
        if module_name in stdlib_modules:
            continue
        
        # 检查是否是已知的第三方包
        if module_name in package_mapping:
            missing_packages.add(package_mapping[module_name])
        elif module_name not in stdlib_modules:
            # 未知模块，假设包名与模块名相同
            missing_packages.add(module_name)
    
    return missing_packages


def format_error_context(
    code: str,
    error_message: str,
    error_line: Optional[int] = None,
    context_lines: int = 3
) -> str:
    """
    格式化错误上下文，高亮显示错误行
    
    Args:
        code: 完整代码
        error_message: 错误信息
        error_line: 错误行号（从1开始）
        context_lines: 上下文行数
        
    Returns:
        格式化的错误上下文字符串
    """
    lines = code.split('\n')
    
    # 尝试从错误信息中提取行号
    if error_line is None:
        line_match = re.search(r'line\s+(\d+)', error_message, re.IGNORECASE)
        if line_match:
            error_line = int(line_match.group(1))
    
    output = ["=" * 60]
    output.append("错误信息:")
    output.append(error_message)
    output.append("=" * 60)
    
    if error_line and 1 <= error_line <= len(lines):
        output.append(f"\n错误位置 (第 {error_line} 行):")
        output.append("-" * 40)
        
        start = max(0, error_line - context_lines - 1)
        end = min(len(lines), error_line + context_lines)
        
        for i in range(start, end):
            line_no = i + 1
            prefix = ">>>" if line_no == error_line else "   "
            output.append(f"{prefix} {line_no:4d} | {lines[i]}")
        
        output.append("-" * 40)
    
    return '\n'.join(output)


def sanitize_code(code: str) -> str:
    """
    清洗代码，移除潜在危险操作
    
    Args:
        code: 原始代码
        
    Returns:
        清洗后的代码
    """
    # 危险模式（可根据需求调整）
    dangerous_patterns = [
        # 系统操作
        (r'os\.system\s*\(', '# [BLOCKED] os.system('),
        (r'subprocess\.(?:run|call|Popen)\s*\(', '# [BLOCKED] subprocess.'),
        (r'eval\s*\(', '# [BLOCKED] eval('),
        (r'exec\s*\(', '# [BLOCKED] exec('),
        (r'__import__\s*\(', '# [BLOCKED] __import__('),
        # 文件删除（保留写入）
        (r'shutil\.rmtree\s*\(', '# [BLOCKED] shutil.rmtree('),
        (r'os\.remove\s*\(', '# [BLOCKED] os.remove('),
        (r'os\.unlink\s*\(', '# [BLOCKED] os.unlink('),
        (r'os\.rmdir\s*\(', '# [BLOCKED] os.rmdir('),
    ]
    
    sanitized = code
    for pattern, replacement in dangerous_patterns:
        sanitized = re.sub(pattern, replacement, sanitized)
    
    return sanitized


def get_code_hash(code: str) -> str:
    """
    获取代码的哈希值，用于缓存和去重
    
    Args:
        code: Python 代码
        
    Returns:
        MD5 哈希值
    """
    # 规范化代码（移除空白差异）
    normalized = '\n'.join(line.rstrip() for line in code.split('\n') if line.strip())
    return hashlib.md5(normalized.encode()).hexdigest()[:12]


def parse_traceback(traceback_str: str) -> Dict:
    """
    解析 Python traceback 信息
    
    Args:
        traceback_str: 完整的 traceback 字符串
        
    Returns:
        解析后的结构化信息
    """
    result = {
        'error_type': None,
        'error_message': None,
        'error_line': None,
        'error_file': None,
        'stack_trace': [],
        'raw': traceback_str
    }
    
    lines = traceback_str.strip().split('\n')
    
    # 提取最后一行的错误类型和消息
    if lines:
        last_line = lines[-1]
        error_match = re.match(r'(\w+(?:Error|Exception|Warning)?)\s*:\s*(.*)', last_line)
        if error_match:
            result['error_type'] = error_match.group(1)
            result['error_message'] = error_match.group(2)
    
    # 提取文件和行号信息
    file_line_pattern = r'File\s+"([^"]+)",\s+line\s+(\d+)'
    for line in lines:
        match = re.search(file_line_pattern, line)
        if match:
            result['stack_trace'].append({
                'file': match.group(1),
                'line': int(match.group(2))
            })
    
    # 最后一个文件/行号通常是实际错误位置
    if result['stack_trace']:
        last_trace = result['stack_trace'][-1]
        result['error_file'] = last_trace['file']
        result['error_line'] = last_trace['line']
    
    return result


def suggest_fixes(error_type: str, error_message: str) -> List[str]:
    """
    根据错误类型提供修复建议
    
    Args:
        error_type: 错误类型
        error_message: 错误消息
        
    Returns:
        建议列表
    """
    suggestions = []
    
    error_type_lower = error_type.lower() if error_type else ''
    error_msg_lower = error_message.lower() if error_message else ''
    
    if 'keyerror' in error_type_lower:
        suggestions.append("检查字典/DataFrame 的键名是否正确")
        suggestions.append("使用 .get() 方法或 'in' 检查键是否存在")
        suggestions.append("打印所有可用的键名: print(df.columns.tolist()) 或 print(dict.keys())")
    
    elif 'indexerror' in error_type_lower:
        suggestions.append("检查列表/数组的索引是否越界")
        suggestions.append("先打印长度确认: print(len(data))")
    
    elif 'typeerror' in error_type_lower:
        suggestions.append("检查变量类型是否正确")
        suggestions.append("可能需要类型转换: int(), str(), float(), list()")
        if 'nonetype' in error_msg_lower:
            suggestions.append("某个变量是 None，检查其来源")
    
    elif 'valueerror' in error_type_lower:
        suggestions.append("检查输入值是否在有效范围内")
        suggestions.append("可能存在空值或异常值，尝试 dropna() 或数据清洗")
    
    elif 'filenotfounderror' in error_type_lower:
        suggestions.append("确认文件路径和文件名是否正确")
        suggestions.append("检查文件是否存在: os.path.exists(filepath)")
        suggestions.append("打印当前工作目录: print(os.getcwd())")
    
    elif 'modulenotfounderror' in error_type_lower or 'importerror' in error_type_lower:
        suggestions.append("需要安装缺失的包")
        match = re.search(r"No module named '(\w+)'", error_message)
        if match:
            suggestions.append(f"尝试: pip install {match.group(1)}")
    
    elif 'attributeerror' in error_type_lower:
        suggestions.append("检查对象是否有该属性或方法")
        suggestions.append("确认对象类型: print(type(obj))")
    
    elif 'nameerror' in error_type_lower:
        suggestions.append("变量未定义，检查拼写或作用域")
        suggestions.append("确保变量在使用前已赋值")
    
    elif 'syntaxerror' in error_type_lower:
        suggestions.append("检查语法错误：括号匹配、冒号、缩进等")
    
    elif 'unicodedecodeerror' in error_type_lower or 'unicodeencodeerror' in error_type_lower:
        suggestions.append("尝试指定正确的编码: encoding='utf-8' 或 encoding='gbk'")
    
    elif 'memoryerror' in error_type_lower:
        suggestions.append("数据量太大，考虑分批处理或使用 chunksize 参数")
    
    elif 'zerodivisionerror' in error_type_lower:
        suggestions.append("除数为零，添加检查: if divisor != 0")
    
    if not suggestions:
        suggestions.append("仔细阅读错误信息，定位问题代码行")
        suggestions.append("使用 print() 打印中间变量进行调试")
    
    return suggestions
