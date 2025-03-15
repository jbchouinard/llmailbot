import abc
import multiprocessing
import multiprocessing.managers
import queue
from typing import Generic, TypeVar

from jbmailbot.config import ConcurrencyType, MessageQueueType, QueueConfig

T = TypeVar("T")


class AnyQueue(abc.ABC, Generic[T]):
    @abc.abstractmethod
    def is_thread_safe(self) -> bool:
        pass

    @abc.abstractmethod
    def is_process_safe(self) -> bool:
        pass

    @abc.abstractmethod
    def put(self, message: T) -> None:
        pass

    @abc.abstractmethod
    def get(self, block: bool = True, timeout: float | None = None) -> T | None:
        pass


class ThreadQueue(AnyQueue[T]):
    def __init__(self, maxsize: int = 0):
        self.msgq = queue.Queue(maxsize=maxsize)

    def is_thread_safe(self) -> bool:
        return True

    def is_process_safe(self) -> bool:
        return False

    def put(self, message: T) -> None:
        self.msgq.put(message)

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


class ManagedQueue(AnyQueue[T]):
    def __init__(self, maxsize: int = 0):
        self.msgq = get_manager().Queue(maxsize=maxsize)

    def is_thread_safe(self) -> bool:
        return True

    def is_process_safe(self) -> bool:
        return True

    def put(self, message: T) -> None:
        self.msgq.put(message)

    def get(self, block: bool = True, timeout: float | None = None) -> T | None:
        try:
            return self.msgq.get(block=block, timeout=timeout)
        except queue.Empty:
            return None


DEFAULT_QUEUE_TYPE = {
    ConcurrencyType.THREAD: MessageQueueType.THREAD,
    ConcurrencyType.PROCESS: MessageQueueType.PROCESS,
}

QUEUE_TYPE_TO_CLS = {
    MessageQueueType.THREAD: ThreadQueue,
    MessageQueueType.PROCESS: ManagedQueue,
}


def make_queue[T](config: QueueConfig, concurrency_type: ConcurrencyType) -> AnyQueue[T]:
    queue_type = config.queue_type or DEFAULT_QUEUE_TYPE[concurrency_type]
    queue_cls = QUEUE_TYPE_TO_CLS[queue_type]
    return queue_cls(**config.parameters)
