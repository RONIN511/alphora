import asyncio
import logging
from typing import Optional

from .memory_pool import MemoryPool

logger = logging.getLogger(__name__)


class BackgroundTaskManager:
    """后台任务管理器"""

    def __init__(self):
        self._cleanup_task: Optional[asyncio.Task] = None

    def start_memory_cleanup_task(
            self,
            memory_pool: MemoryPool,
            interval: int
    ) -> None:
        """
        启动记忆池清理任务
        :param memory_pool: 记忆池实例
        :param interval: 清理间隔（秒）
        """
        async def cleanup_task():
            """记忆池清理任务"""
            while True:
                try:
                    removed = memory_pool.clean_expired()
                    if removed > 0:
                        logger.info(f"记忆池清理完成，共清理 {removed} 个过期会话")
                except Exception as e:
                    logger.error("记忆池清理任务异常", exc_info=e)
                await asyncio.sleep(interval)

        self._cleanup_task = asyncio.create_task(cleanup_task())
        logger.info(f"记忆池清理任务已启动（间隔: {interval}秒，任务ID: {id(self._cleanup_task)}）")

    async def stop_all_tasks(self) -> None:
        """停止所有后台任务"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                logger.info("记忆池清理任务已取消")
        logger.info("所有后台任务已停止")

