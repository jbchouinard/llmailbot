import abc
import multiprocessing
import multiprocessing.managers
import queue
from typing import Generic, TypeVar

from llmailbot.config import QueueConfig, QueueType

T = TypeVar("T")


class AnyQueue(abc.ABC, Generic[T]):
    @abc.abstractmethod
    def is_thread_safe(self) -> bool:
        pass

    @abc.abstractmethod
    def is_process_safe(self) -> bool:
        pass

    @abc.abstractmethod
    def put(self, message: T, block: bool = True, timeout: float | None = None) -> None:
        pass

    @abc.abstractmethod
    def get(self, block: bool = True, timeout: float | None = None) -> T | None:
        pass


class MemoryQueue(AnyQueue[T]):
    def __init__(self, maxsize: int = 0):
        self.msgq = queue.Queue(maxsize=maxsize)

    def is_thread_safe(self) -> bool:
        return True

    def is_process_safe(self) -> bool:
        return False

    def put(self, message: T, block: bool = True, timeout: float | None = None) -> None:
        self.msgq.put(message, block=block, timeout=timeout)

    def get(self, block: bool = True, timeout: float | None = None) -> T | None:
        try:
            return self.msgq.get(block=block, timeout=timeout)
        except queue.Empty:
            return None


_manager = None


def get_manager() -> multiprocessing.managers.SyncManager:
    global _manager
    if _manager is None:
        _manager = multiprocessing.Manager()
    return _manager


class ManagedMemoryQueue(AnyQueue[T]):
    def __init__(self, maxsize: int = 0):
        self.msgq = get_manager().Queue(maxsize=maxsize)

    def is_thread_safe(self) -> bool:
        return True

    def is_process_safe(self) -> bool:
        return True

    def put(self, message: T, block: bool = True, timeout: float | None = None) -> None:
        self.msgq.put(message, block=block, timeout=timeout)

    def get(self, block: bool = True, timeout: float | None = None) -> T | None:
        try:
            return self.msgq.get(block=block, timeout=timeout)
        except queue.Empty:
            return None


QUEUE_TYPE_TO_CLS = {
    QueueType.MEMORY: MemoryQueue,
    QueueType.MANAGED_MEMORY: ManagedMemoryQueue,
}


def make_queue(config: QueueConfig) -> AnyQueue:
    queue_type = config.queue_type
    if queue_type is None:
        raise ValueError("Queue type must be specified")
    queue_cls = QUEUE_TYPE_TO_CLS[queue_type]
    return queue_cls[T](**config.parameters)
