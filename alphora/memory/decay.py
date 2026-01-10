"""
记忆衰减策略模块

支持多种衰减策略：
- 线性衰减
- 指数衰减
- 对数衰减
- 时间衰减
- 复合衰减
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import math
import time

from alphora.memory.memory_unit import MemoryUnit


class DecayStrategy(ABC):
    """衰减策略抽象基类"""
    
    @abstractmethod
    def calculate_decay_factor(
        self,
        memory: MemoryUnit,
        current_turn: int,
        memory_turn: int
    ) -> float:
        """
        计算衰减因子
        
        Args:
            memory: 记忆单元
            current_turn: 当前对话轮数
            memory_turn: 记忆所在轮数
            
        Returns:
            衰减因子 (0, 1]，用于乘以当前分数
        """
        pass
    
    def apply(
        self,
        memory: MemoryUnit,
        current_turn: int,
        memory_turn: int
    ) -> float:
        """
        应用衰减
        
        Args:
            memory: 记忆单元
            current_turn: 当前对话轮数
            memory_turn: 记忆所在轮数
            
        Returns:
            衰减后的分数
        """
        factor = self.calculate_decay_factor(memory, current_turn, memory_turn)
        return memory.decay(factor)
    
    @property
    @abstractmethod
    def name(self) -> str:
        """策略名称"""
        pass


class LinearDecay(DecayStrategy):
    """
    线性衰减
    
    分数随距离线性减少
    factor = 1 - rate * distance
    """
    
    def __init__(self, rate: float = 0.1):
        """
        Args:
            rate: 每轮衰减的比率
        """
        self.rate = rate
    
    def calculate_decay_factor(
        self,
        memory: MemoryUnit,
        current_turn: int,
        memory_turn: int
    ) -> float:
        distance = current_turn - memory_turn
        if distance <= 0:
            return 1.0
        factor = 1.0 - self.rate * distance
        return max(0.0, factor)
    
    @property
    def name(self) -> str:
        return "linear"


class ExponentialDecay(DecayStrategy):
    """
    指数衰减
    
    分数指数级减少
    factor = base ^ distance
    """
    
    def __init__(self, base: float = 0.9):
        """
        Args:
            base: 衰减基数 (0, 1)
        """
        self.base = base
    
    def calculate_decay_factor(
        self,
        memory: MemoryUnit,
        current_turn: int,
        memory_turn: int
    ) -> float:
        distance = current_turn - memory_turn
        if distance <= 0:
            return 1.0
        return self.base ** distance
    
    @property
    def name(self) -> str:
        return "exponential"


class LogarithmicDecay(DecayStrategy):
    """
    对数衰减
    
    衰减速度随距离增加而减慢
    factor = 1 / (1 + log(distance + 1))
    """
    
    def __init__(self, scale: float = 1.0):
        """
        Args:
            scale: 缩放系数
        """
        self.scale = scale
    
    def calculate_decay_factor(
        self,
        memory: MemoryUnit,
        current_turn: int,
        memory_turn: int
    ) -> float:
        distance = current_turn - memory_turn
        if distance <= 0:
            return 1.0
        return 1.0 / (1.0 + self.scale * math.log(distance + 1))
    
    @property
    def name(self) -> str:
        return "logarithmic"


class TimeBasedDecay(DecayStrategy):
    """
    基于时间的衰减
    
    根据实际经过的时间而非对话轮数衰减
    factor = 0.5 ^ (elapsed_time / half_life)
    """
    
    def __init__(self, half_life: float = 3600):
        """
        Args:
            half_life: 半衰期（秒），默认1小时
        """
        self.half_life = half_life
    
    def calculate_decay_factor(
        self,
        memory: MemoryUnit,
        current_turn: int,
        memory_turn: int
    ) -> float:
        elapsed = time.time() - memory.timestamp
        if elapsed <= 0:
            return 1.0
        return 0.5 ** (elapsed / self.half_life)
    
    @property
    def name(self) -> str:
        return "time_based"


class ImportanceAwareDecay(DecayStrategy):
    """
    重要性感知衰减
    
    重要的记忆衰减更慢
    factor = base_factor ^ (1 - importance)
    """
    
    def __init__(
        self,
        base_strategy: Optional[DecayStrategy] = None,
        importance_factor: float = 0.5
    ):
        """
        Args:
            base_strategy: 基础衰减策略
            importance_factor: 重要性影响系数
        """
        self.base_strategy = base_strategy or ExponentialDecay()
        self.importance_factor = importance_factor
    
    def calculate_decay_factor(
        self,
        memory: MemoryUnit,
        current_turn: int,
        memory_turn: int
    ) -> float:
        base_factor = self.base_strategy.calculate_decay_factor(
            memory, current_turn, memory_turn
        )
        
        # 重要性越高，衰减越慢
        importance_boost = self.importance_factor * memory.importance
        adjusted_factor = base_factor ** (1.0 - importance_boost)
        
        return min(1.0, adjusted_factor)
    
    @property
    def name(self) -> str:
        return f"importance_aware({self.base_strategy.name})"


class AdaptiveDecay(DecayStrategy):
    """
    自适应衰减
    
    根据访问频率调整衰减速度
    经常访问的记忆衰减更慢
    """
    
    def __init__(
        self,
        base_strategy: Optional[DecayStrategy] = None,
        access_factor: float = 0.1
    ):
        """
        Args:
            base_strategy: 基础衰减策略
            access_factor: 访问次数影响系数
        """
        self.base_strategy = base_strategy or ExponentialDecay()
        self.access_factor = access_factor
    
    def calculate_decay_factor(
        self,
        memory: MemoryUnit,
        current_turn: int,
        memory_turn: int
    ) -> float:
        base_factor = self.base_strategy.calculate_decay_factor(
            memory, current_turn, memory_turn
        )
        
        # 访问次数越多，衰减越慢
        access_boost = min(1.0, self.access_factor * memory.access_count)
        adjusted_factor = base_factor ** (1.0 - access_boost)
        
        return min(1.0, adjusted_factor)
    
    @property
    def name(self) -> str:
        return f"adaptive({self.base_strategy.name})"


class CompositeDecay(DecayStrategy):
    """
    复合衰减
    
    结合多种衰减策略
    """
    
    def __init__(
        self,
        strategies: Dict[DecayStrategy, float] = None
    ):
        """
        Args:
            strategies: {策略: 权重} 字典
        """
        if strategies is None:
            strategies = {
                ExponentialDecay(): 0.5,
                TimeBasedDecay(): 0.3,
                ImportanceAwareDecay(): 0.2
            }
        
        self.strategies = strategies
        
        # 归一化权重
        total_weight = sum(strategies.values())
        self.weights = {s: w / total_weight for s, w in strategies.items()}
    
    def calculate_decay_factor(
        self,
        memory: MemoryUnit,
        current_turn: int,
        memory_turn: int
    ) -> float:
        weighted_sum = 0.0
        
        for strategy, weight in self.weights.items():
            factor = strategy.calculate_decay_factor(
                memory, current_turn, memory_turn
            )
            weighted_sum += factor * weight
        
        return weighted_sum
    
    @property
    def name(self) -> str:
        names = [s.name for s in self.strategies.keys()]
        return f"composite({'+'.join(names)})"


class NoDecay(DecayStrategy):
    """
    不衰减
    
    用于长期记忆等不需要衰减的场景
    """
    
    def calculate_decay_factor(
        self,
        memory: MemoryUnit,
        current_turn: int,
        memory_turn: int
    ) -> float:
        return 1.0
    
    @property
    def name(self) -> str:
        return "no_decay"


# ==================== 工厂函数 ====================

_DECAY_STRATEGIES = {
    "linear": LinearDecay,
    "exponential": ExponentialDecay,
    "exp": ExponentialDecay,
    "logarithmic": LogarithmicDecay,
    "log": LogarithmicDecay,
    "time": TimeBasedDecay,
    "time_based": TimeBasedDecay,
    "importance": ImportanceAwareDecay,
    "adaptive": AdaptiveDecay,
    "composite": CompositeDecay,
    "none": NoDecay,
    "no_decay": NoDecay,
}


def get_decay_strategy(
    name: str = "log",
    **kwargs
) -> DecayStrategy:
    """
    获取衰减策略实例
    
    Args:
        name: 策略名称
        **kwargs: 传递给策略构造函数的参数
        
    Returns:
        DecayStrategy实例
        
    示例:
    ```python
    # 获取对数衰减策略
    strategy = get_decay_strategy("log")
    
    # 获取指数衰减策略，自定义基数
    strategy = get_decay_strategy("exponential", base=0.95)
    
    # 获取时间衰减策略，自定义半衰期
    strategy = get_decay_strategy("time", half_life=7200)
    ```
    """
    if name not in _DECAY_STRATEGIES:
        raise ValueError(
            f"Unknown decay strategy: {name}. "
            f"Available: {list(_DECAY_STRATEGIES.keys())}"
        )
    
    return _DECAY_STRATEGIES[name](**kwargs)


def list_decay_strategies() -> Dict[str, str]:
    """列出所有可用的衰减策略"""
    return {
        "linear": "线性衰减 - 分数随距离线性减少",
        "exponential": "指数衰减 - 分数指数级减少",
        "logarithmic": "对数衰减 - 衰减速度随距离增加而减慢",
        "time_based": "时间衰减 - 基于实际时间而非轮数",
        "importance": "重要性感知 - 重要记忆衰减更慢",
        "adaptive": "自适应衰减 - 常访问的记忆衰减更慢",
        "composite": "复合衰减 - 结合多种策略",
        "no_decay": "不衰减 - 分数保持不变",
    }
