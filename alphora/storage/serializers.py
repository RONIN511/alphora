"""
序列化器模块

支持多种序列化格式，用于存储数据的编码和解码
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, Type
import json
import pickle
from dataclasses import dataclass, asdict, is_dataclass
from datetime import datetime
import base64


class SerializationError(Exception):
    """序列化错误"""
    pass


class DeserializationError(Exception):
    """反序列化错误"""
    pass


class Serializer(ABC):
    """序列化器抽象基类"""
    
    @abstractmethod
    def serialize(self, data: Any) -> bytes:
        """将数据序列化为字节"""
        pass
    
    @abstractmethod
    def deserialize(self, data: bytes) -> Any:
        """将字节反序列化为数据"""
        pass
    
    def serialize_to_string(self, data: Any) -> str:
        """序列化为字符串"""
        return base64.b64encode(self.serialize(data)).decode('utf-8')
    
    def deserialize_from_string(self, data: str) -> Any:
        """从字符串反序列化"""
        return self.deserialize(base64.b64decode(data.encode('utf-8')))


class JSONSerializer(Serializer):
    """
    JSON序列化器
    
    支持基本类型、列表、字典，以及通过自定义编码器扩展的类型
    """
    
    def __init__(self, indent: Optional[int] = None, ensure_ascii: bool = False):
        self.indent = indent
        self.ensure_ascii = ensure_ascii
    
    def serialize(self, data: Any) -> bytes:
        try:
            return json.dumps(
                data,
                cls=ExtendedJSONEncoder,
                indent=self.indent,
                ensure_ascii=self.ensure_ascii
            ).encode('utf-8')
        except (TypeError, ValueError) as e:
            raise SerializationError(f"JSON serialization failed: {e}")
    
    def deserialize(self, data: bytes) -> Any:
        try:
            return json.loads(
                data.decode('utf-8'),
                object_hook=extended_json_decoder
            )
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise DeserializationError(f"JSON deserialization failed: {e}")
    
    def serialize_to_string(self, data: Any) -> str:
        """JSON直接序列化为字符串"""
        try:
            return json.dumps(
                data,
                cls=ExtendedJSONEncoder,
                indent=self.indent,
                ensure_ascii=self.ensure_ascii
            )
        except (TypeError, ValueError) as e:
            raise SerializationError(f"JSON serialization failed: {e}")
    
    def deserialize_from_string(self, data: str) -> Any:
        """从JSON字符串反序列化"""
        try:
            return json.loads(data, object_hook=extended_json_decoder)
        except json.JSONDecodeError as e:
            raise DeserializationError(f"JSON deserialization failed: {e}")


class PickleSerializer(Serializer):
    """
    Pickle序列化器
    
    支持任意Python对象，但不安全，仅用于受信任的数据
    """
    
    def __init__(self, protocol: int = pickle.HIGHEST_PROTOCOL):
        self.protocol = protocol
    
    def serialize(self, data: Any) -> bytes:
        try:
            return pickle.dumps(data, protocol=self.protocol)
        except (pickle.PicklingError, TypeError) as e:
            raise SerializationError(f"Pickle serialization failed: {e}")
    
    def deserialize(self, data: bytes) -> Any:
        try:
            return pickle.loads(data)
        except (pickle.UnpicklingError, Exception) as e:
            raise DeserializationError(f"Pickle deserialization failed: {e}")


class ExtendedJSONEncoder(json.JSONEncoder):
    """
    扩展的JSON编码器
    
    支持:
    - dataclass
    - datetime
    - bytes
    - set
    - 自定义对象（通过 __json__ 方法）
    """
    
    def default(self, obj: Any) -> Any:
        # dataclass
        if is_dataclass(obj) and not isinstance(obj, type):
            return {
                "__dataclass__": obj.__class__.__name__,
                "__module__": obj.__class__.__module__,
                "data": asdict(obj)
            }
        
        # datetime
        if isinstance(obj, datetime):
            return {
                "__datetime__": True,
                "iso": obj.isoformat()
            }
        
        # bytes
        if isinstance(obj, bytes):
            return {
                "__bytes__": True,
                "data": base64.b64encode(obj).decode('ascii')
            }
        
        # set
        if isinstance(obj, set):
            return {
                "__set__": True,
                "data": list(obj)
            }
        
        # 自定义对象
        if hasattr(obj, '__json__'):
            return {
                "__custom__": obj.__class__.__name__,
                "__module__": obj.__class__.__module__,
                "data": obj.__json__()
            }
        
        # 尝试转换为字典
        if hasattr(obj, '__dict__'):
            return {
                "__object__": obj.__class__.__name__,
                "__module__": obj.__class__.__module__,
                "data": obj.__dict__
            }
        
        return super().default(obj)


def extended_json_decoder(dct: dict) -> Any:
    """扩展的JSON解码器"""
    
    # datetime
    if "__datetime__" in dct:
        return datetime.fromisoformat(dct["iso"])
    
    # bytes
    if "__bytes__" in dct:
        return base64.b64decode(dct["data"])
    
    # set
    if "__set__" in dct:
        return set(dct["data"])
    
    # 注意：dataclass、custom、object 类型需要额外处理
    # 这里保留元数据，由上层根据需要恢复
    
    return dct


# ==================== 工具函数 ====================

def get_serializer(name: str = "json", **kwargs) -> Serializer:
    """
    获取序列化器实例
    
    Args:
        name: 序列化器名称 (json, pickle)
        **kwargs: 传递给序列化器的参数
        
    Returns:
        Serializer实例
    """
    serializers = {
        "json": JSONSerializer,
        "pickle": PickleSerializer,
    }
    
    if name not in serializers:
        raise ValueError(f"Unknown serializer: {name}. Available: {list(serializers.keys())}")
    
    return serializers[name](**kwargs)


def safe_serialize(data: Any, serializer: Optional[Serializer] = None) -> str:
    """
    安全地序列化数据为字符串
    
    尝试使用JSON，失败则回退到pickle的base64编码
    """
    if serializer is None:
        serializer = JSONSerializer()
    
    try:
        return serializer.serialize_to_string(data)
    except SerializationError:
        # 回退到pickle
        pickle_serializer = PickleSerializer()
        return "__pickle__:" + pickle_serializer.serialize_to_string(data)


def safe_deserialize(data: str, serializer: Optional[Serializer] = None) -> Any:
    """
    安全地从字符串反序列化数据
    """
    if data.startswith("__pickle__:"):
        pickle_serializer = PickleSerializer()
        return pickle_serializer.deserialize_from_string(data[11:])
    
    if serializer is None:
        serializer = JSONSerializer()
    
    return serializer.deserialize_from_string(data)
