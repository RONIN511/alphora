"""
记忆检索策略模块

支持多种检索方式：
- 关键词匹配
- 模糊匹配
- 正则匹配
- 标签匹配
- 时间范围检索
- 综合检索
"""

from abc import ABC, abstractmethod
from typing import List, Tuple, Optional, Set, Dict, Any, Callable
from dataclasses import dataclass
import re
import time
from difflib import SequenceMatcher

from alphora.memory.memory_unit import MemoryUnit


@dataclass
class RetrievalResult:
    """检索结果"""
    memory: MemoryUnit
    score: float  # 匹配分数
    match_reason: str  # 匹配原因
    
    def __repr__(self):
        return f"RetrievalResult(score={self.score:.3f}, reason={self.match_reason})"


class RetrievalStrategy(ABC):
    """检索策略抽象基类"""
    
    @abstractmethod
    def search(
        self,
        query: str,
        memories: List[MemoryUnit],
        top_k: int = 10
    ) -> List[RetrievalResult]:
        """
        搜索记忆
        
        Args:
            query: 查询字符串
            memories: 记忆列表
            top_k: 返回数量
            
        Returns:
            检索结果列表，按分数降序排列
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """策略名称"""
        pass


class KeywordRetrieval(RetrievalStrategy):
    """
    关键词检索
    
    精确匹配查询中的关键词
    """
    
    def __init__(self, case_sensitive: bool = False):
        """
        Args:
            case_sensitive: 是否区分大小写
        """
        self.case_sensitive = case_sensitive
    
    def _tokenize(self, text: str) -> Set[str]:
        """分词"""
        if not self.case_sensitive:
            text = text.lower()
        # 简单分词：按空格和标点分割
        tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9]+', text)
        return set(tokens)
    
    def search(
        self,
        query: str,
        memories: List[MemoryUnit],
        top_k: int = 10
    ) -> List[RetrievalResult]:
        query_tokens = self._tokenize(query)
        
        if not query_tokens:
            return []
        
        results = []
        
        for memory in memories:
            content = memory.get_content_text()
            content_tokens = self._tokenize(content)
            
            # 计算匹配的token数
            matched = query_tokens & content_tokens
            
            if matched:
                # 分数 = 匹配数 / 查询token数
                score = len(matched) / len(query_tokens)
                
                # 考虑记忆的综合分数
                final_score = 0.7 * score + 0.3 * memory.get_composite_score()
                
                results.append(RetrievalResult(
                    memory=memory,
                    score=final_score,
                    match_reason=f"keywords: {', '.join(list(matched)[:3])}"
                ))
        
        # 按分数排序
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]
    
    @property
    def name(self) -> str:
        return "keyword"


class FuzzyRetrieval(RetrievalStrategy):
    """
    模糊检索
    
    使用编辑距离进行模糊匹配
    """
    
    def __init__(self, threshold: float = 0.6):
        """
        Args:
            threshold: 相似度阈值
        """
        self.threshold = threshold
    
    def _similarity(self, s1: str, s2: str) -> float:
        """计算字符串相似度"""
        return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()
    
    def search(
        self,
        query: str,
        memories: List[MemoryUnit],
        top_k: int = 10
    ) -> List[RetrievalResult]:
        results = []
        
        for memory in memories:
            content = memory.get_content_text()
            
            # 计算整体相似度
            similarity = self._similarity(query, content)
            
            # 也检查是否包含相似的子串
            if len(query) < len(content):
                # 滑动窗口匹配
                window_size = len(query)
                for i in range(len(content) - window_size + 1):
                    window = content[i:i + window_size]
                    window_sim = self._similarity(query, window)
                    similarity = max(similarity, window_sim)
            
            if similarity >= self.threshold:
                final_score = 0.7 * similarity + 0.3 * memory.get_composite_score()
                
                results.append(RetrievalResult(
                    memory=memory,
                    score=final_score,
                    match_reason=f"fuzzy_match: {similarity:.2f}"
                ))
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]
    
    @property
    def name(self) -> str:
        return "fuzzy"


class RegexRetrieval(RetrievalStrategy):
    """
    正则表达式检索
    """
    
    def __init__(self, flags: int = re.IGNORECASE):
        """
        Args:
            flags: 正则表达式标志
        """
        self.flags = flags
    
    def search(
        self,
        query: str,
        memories: List[MemoryUnit],
        top_k: int = 10
    ) -> List[RetrievalResult]:
        try:
            pattern = re.compile(query, self.flags)
        except re.error:
            # 如果不是有效的正则，回退到简单匹配
            pattern = re.compile(re.escape(query), self.flags)
        
        results = []
        
        for memory in memories:
            content = memory.get_content_text()
            matches = pattern.findall(content)
            
            if matches:
                # 分数基于匹配数量
                score = min(1.0, len(matches) * 0.2)
                final_score = 0.7 * score + 0.3 * memory.get_composite_score()
                
                results.append(RetrievalResult(
                    memory=memory,
                    score=final_score,
                    match_reason=f"regex: {len(matches)} matches"
                ))
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]
    
    @property
    def name(self) -> str:
        return "regex"


class TagRetrieval(RetrievalStrategy):
    """
    标签检索
    
    根据记忆的标签进行匹配
    """
    
    def search(
        self,
        query: str,
        memories: List[MemoryUnit],
        top_k: int = 10
    ) -> List[RetrievalResult]:
        # 将查询分割为标签
        query_tags = set(tag.strip().lower() for tag in re.split(r'[,\s]+', query) if tag.strip())
        
        if not query_tags:
            return []
        
        results = []
        
        for memory in memories:
            memory_tags = set(tag.lower() for tag in memory.tags)
            matched_tags = query_tags & memory_tags
            
            if matched_tags:
                score = len(matched_tags) / len(query_tags)
                final_score = 0.6 * score + 0.4 * memory.get_composite_score()
                
                results.append(RetrievalResult(
                    memory=memory,
                    score=final_score,
                    match_reason=f"tags: {', '.join(matched_tags)}"
                ))
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]
    
    @property
    def name(self) -> str:
        return "tag"


class TimeRangeRetrieval(RetrievalStrategy):
    """
    时间范围检索
    
    支持相对时间查询，如"最近1小时"、"yesterday"
    """
    
    # 时间表达式映射（秒）
    TIME_EXPRESSIONS = {
        # 中文
        '刚才': 300,
        '刚刚': 300,
        '最近': 3600,
        '今天': 86400,
        '昨天': 172800,
        '前天': 259200,
        '这周': 604800,
        '本周': 604800,
        '上周': 1209600,
        '这个月': 2592000,
        '本月': 2592000,
        '上个月': 5184000,
        # 英文
        'now': 300,
        'recent': 3600,
        'today': 86400,
        'yesterday': 172800,
        'this week': 604800,
        'last week': 1209600,
        'this month': 2592000,
        'last month': 5184000,
    }
    
    def _parse_time_range(self, query: str) -> Optional[Tuple[float, float]]:
        """解析时间范围"""
        query_lower = query.lower()
        
        # 检查预定义表达式
        for expr, seconds in self.TIME_EXPRESSIONS.items():
            if expr in query_lower:
                now = time.time()
                return (now - seconds, now)
        
        # 尝试解析 "最近N小时/天/周"
        patterns = [
            (r'最近(\d+)小时', 3600),
            (r'最近(\d+)天', 86400),
            (r'最近(\d+)周', 604800),
            (r'last (\d+) hours?', 3600),
            (r'last (\d+) days?', 86400),
            (r'last (\d+) weeks?', 604800),
        ]
        
        for pattern, unit in patterns:
            match = re.search(pattern, query_lower)
            if match:
                num = int(match.group(1))
                now = time.time()
                return (now - num * unit, now)
        
        return None
    
    def search(
        self,
        query: str,
        memories: List[MemoryUnit],
        top_k: int = 10
    ) -> List[RetrievalResult]:
        time_range = self._parse_time_range(query)
        
        if time_range is None:
            return []
        
        start_time, end_time = time_range
        results = []
        
        for memory in memories:
            if start_time <= memory.timestamp <= end_time:
                # 越新的记忆分数越高
                recency = (memory.timestamp - start_time) / (end_time - start_time)
                final_score = 0.5 * recency + 0.5 * memory.get_composite_score()
                
                results.append(RetrievalResult(
                    memory=memory,
                    score=final_score,
                    match_reason=f"time: {memory.formatted_timestamp()}"
                ))
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]
    
    @property
    def name(self) -> str:
        return "time_range"


class HybridRetrieval(RetrievalStrategy):
    """
    混合检索
    
    结合多种检索策略
    """
    
    def __init__(
        self,
        strategies: Optional[Dict[RetrievalStrategy, float]] = None
    ):
        """
        Args:
            strategies: {策略: 权重} 字典
        """
        if strategies is None:
            strategies = {
                KeywordRetrieval(): 0.4,
                FuzzyRetrieval(): 0.3,
                TagRetrieval(): 0.3,
            }
        
        self.strategies = strategies
        
        # 归一化权重
        total = sum(strategies.values())
        self.weights = {s: w / total for s, w in strategies.items()}
    
    def search(
        self,
        query: str,
        memories: List[MemoryUnit],
        top_k: int = 10
    ) -> List[RetrievalResult]:
        # 收集所有策略的结果
        memory_scores: Dict[str, Tuple[MemoryUnit, float, List[str]]] = {}
        
        for strategy, weight in self.weights.items():
            results = strategy.search(query, memories, top_k=len(memories))
            
            for result in results:
                mid = result.memory.unique_id
                if mid not in memory_scores:
                    memory_scores[mid] = (result.memory, 0.0, [])
                
                _, current_score, reasons = memory_scores[mid]
                memory_scores[mid] = (
                    result.memory,
                    current_score + result.score * weight,
                    reasons + [result.match_reason]
                )
        
        # 构建最终结果
        results = []
        for mid, (memory, score, reasons) in memory_scores.items():
            results.append(RetrievalResult(
                memory=memory,
                score=score,
                match_reason=" | ".join(reasons[:2])  # 只保留前两个原因
            ))
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]
    
    @property
    def name(self) -> str:
        return "hybrid"


class SemanticRetrieval(RetrievalStrategy):
    """
    语义检索（占位实现）
    
    如需真正的语义检索，需要接入向量模型
    这里提供一个基于关键词的近似实现
    """
    
    def __init__(self):
        self._keyword_retrieval = KeywordRetrieval()
        self._fuzzy_retrieval = FuzzyRetrieval(threshold=0.4)
    
    def search(
        self,
        query: str,
        memories: List[MemoryUnit],
        top_k: int = 10
    ) -> List[RetrievalResult]:
        # 组合关键词和模糊匹配结果
        keyword_results = self._keyword_retrieval.search(query, memories, top_k * 2)
        fuzzy_results = self._fuzzy_retrieval.search(query, memories, top_k * 2)
        
        # 合并结果
        memory_scores: Dict[str, Tuple[MemoryUnit, float, str]] = {}
        
        for result in keyword_results:
            mid = result.memory.unique_id
            memory_scores[mid] = (result.memory, result.score * 0.6, result.match_reason)
        
        for result in fuzzy_results:
            mid = result.memory.unique_id
            if mid in memory_scores:
                _, prev_score, prev_reason = memory_scores[mid]
                memory_scores[mid] = (
                    result.memory,
                    prev_score + result.score * 0.4,
                    f"{prev_reason} | {result.match_reason}"
                )
            else:
                memory_scores[mid] = (result.memory, result.score * 0.4, result.match_reason)
        
        results = [
            RetrievalResult(memory=m, score=s, match_reason=r)
            for m, s, r in memory_scores.values()
        ]
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]
    
    @property
    def name(self) -> str:
        return "semantic"


# ==================== 工厂函数 ====================

_RETRIEVAL_STRATEGIES = {
    "keyword": KeywordRetrieval,
    "fuzzy": FuzzyRetrieval,
    "regex": RegexRetrieval,
    "tag": TagRetrieval,
    "time": TimeRangeRetrieval,
    "time_range": TimeRangeRetrieval,
    "hybrid": HybridRetrieval,
    "semantic": SemanticRetrieval,
}


def get_retrieval_strategy(
    name: str = "keyword",
    **kwargs
) -> RetrievalStrategy:
    """
    获取检索策略实例
    
    Args:
        name: 策略名称
        **kwargs: 传递给策略构造函数的参数
        
    Returns:
        RetrievalStrategy实例
    """
    if name not in _RETRIEVAL_STRATEGIES:
        raise ValueError(
            f"Unknown retrieval strategy: {name}. "
            f"Available: {list(_RETRIEVAL_STRATEGIES.keys())}"
        )
    
    return _RETRIEVAL_STRATEGIES[name](**kwargs)


def search_memories(
    query: str,
    memories: List[MemoryUnit],
    strategy: str = "hybrid",
    top_k: int = 10,
    **kwargs
) -> List[RetrievalResult]:
    """
    搜索记忆的便捷函数
    
    Args:
        query: 查询字符串
        memories: 记忆列表
        strategy: 检索策略名称
        top_k: 返回数量
        **kwargs: 传递给策略的参数
        
    Returns:
        检索结果列表
    """
    retriever = get_retrieval_strategy(strategy, **kwargs)
    return retriever.search(query, memories, top_k)
