"""
短期记忆，记忆的衰减 对数
"""

from alphora.memory.base import BaseMemory
from typing import Any, Dict
from alphora.memory.memory_unit import MemoryUnit
import math


class ShortTermMemory(BaseMemory):

    def add_memory(self,
                   role: str,
                   content: str,
                   memory_id: str = 'default',
                   decay_factor: float = 0.9,
                   increment: float = 0.1):
        """
        添加新的记忆，并对现有记忆进行动态衰减

        Args:
            decay_factor: x
            memory_id (str): Prompt 的唯一标识符。
            content (Dict[str, Any]): 新的记忆内容。
            increment (float): 新记忆的增强值。
        """
        # 初始化 Prompt
        if memory_id not in self._memories:
            self._memories[memory_id] = []
            self.current_turn[memory_id] = 0

        # 更新轮数
        self.current_turn[memory_id] += 1
        current_turn = self.current_turn[memory_id]

        # 对现有记忆进行动态衰减
        for turn, memory in enumerate(self._memories[memory_id], start=1):
            distance = current_turn - turn  # 计算距离
            decay_factor = self._log_decay(distance)
            memory.decay(decay_factor)

        # 添加新记忆并增强
        new_memory = MemoryUnit(content={role: content})
        new_memory.reinforce(increment)
        self._memories[memory_id].append(new_memory)

    @staticmethod
    def _log_decay(distance: int) -> float:
        """
        使用对数函数计算衰减因子，距离越远，衰减越大

        Args:
            distance (int): 当前对话轮数与记忆所在轮数的距离

        Returns:
            float: 衰减因子，范围 (0, 1]。
        """
        if distance <= 0:
            return 1.0  # 当前对话不衰减
        return 1 / (1 + math.log(distance + 1))  # 对数衰减因子，随距离增加逐渐变小

