import base64
import binascii
from pathlib import Path


def file_to_base64(file_path: str | Path) -> str:
    """
    将文件转为 Base64 编码字符串
    Args:
        file_path: 文件路径
    Returns:
        Base64编码字符串
    """
    try:
        file_path = Path(file_path)
        with file_path.open('rb') as file:
            return base64.b64encode(file.read()).decode('utf-8')
    except FileNotFoundError:
        raise FileNotFoundError(f"文件未找到: {file_path}")
    except Exception as e:
        raise ValueError(f"处理文件时出错: {e}")


def base64_to_file(base64_str: str, output_file_path: str | Path) -> None:
    """
    将Base64编码字符串转为文件
    Args:
        base64_str: Base64编码字符串
        output_file_path: 输出文件路径
    """
    try:
        output_file_path = Path(output_file_path)
        output_file_path.parent.mkdir(parents=True, exist_ok=True)

        file_data = base64.b64decode(base64_str)
        with output_file_path.open('wb') as file:
            file.write(file_data)
    except (binascii.Error, ValueError):
        raise ValueError(f"无效的Base64字符串")
    except Exception as e:
        raise OSError(f"写入文件时出错: {e}")


