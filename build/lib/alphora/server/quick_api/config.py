from dataclasses import dataclass
from typing import Optional, Type


@dataclass
class APIPublisherConfig:
    """API发布器配置类"""
    # 基础路径
    path: str = "/alphadata"
    # 记忆池配置
    memory_ttl: int = 3600  # 记忆过期时间（秒）
    max_memory_items: int = 1000  # 记忆池最大容量
    auto_clean_interval: int = 600  # 自动清理间隔（秒）
    # API文档配置
    api_title: Optional[str] = None
    api_description: Optional[str] = None

    def __post_init__(self):
        """后置初始化：补全默认文档信息"""
        if self.api_title is None:
            self.api_title = "Alphaora Agent API Service"
        if self.api_description is None:
            self.api_description = "Auto-generated API for Alphaora Agent (per-request new instance)"

