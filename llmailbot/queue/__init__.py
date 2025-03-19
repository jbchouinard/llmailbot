from llmailbot.config import (
    MemoryQueueSettings,
    QueueSettings,
    RedisQueueSettings,
)
from llmailbot.queue.core import AsyncQueue, SyncQueue
from llmailbot.queue.memory import AsyncioQueue, ManagedMemoryQueue, MemoryQueue

try:
    from .redis import AsyncRedisQueue
except ImportError:
    AsyncRedisQueue = None

__all__ = [
    "SyncQueue",
    "make_queue",
    "MemoryQueue",
    "ManagedMemoryQueue",
    "AsyncRedisQueue",
]


def make_queue(config: QueueSettings) -> AsyncQueue:
    if isinstance(config, MemoryQueueSettings):
        return AsyncioQueue(maxsize=config.max_size, timeout=config.timeout)
    if isinstance(config, RedisQueueSettings):
        if AsyncRedisQueue is None:
            raise RuntimeError("RedisQueue not available - redis extra must be installed")
        return AsyncRedisQueue(
            conf=config,
            key=config.key,
            timeout=config.timeout,
        )
