from llmailbot.config import (
    QueueSettings,
)
from llmailbot.enums import QueueType
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
    if config.queue_type == QueueType.MEMORY:
        return AsyncioQueue(maxsize=config.max_size, timeout=config.timeout)
    elif config.queue_type == QueueType.REDIS:
        if AsyncRedisQueue is None:
            raise RuntimeError("RedisQueue not available - redis extra must be installed")
        assert config.key is not None
        return AsyncRedisQueue(
            conf=config,
            key=config.key,
            timeout=config.timeout,
        )
    else:
        raise ValueError(f"Unknown queue type: {config.queue_type}")
