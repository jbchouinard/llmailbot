import asyncio
import multiprocessing
import multiprocessing.managers
import queue

from .core import AsyncQueue, SyncQueue, T


class MemoryQueue(SyncQueue[T]):
    def __init__(self, maxsize: int = 0, timeout: float = 5.0):
        self.msgq = queue.Queue(maxsize=maxsize)
        self.timeout = timeout

    def put(self, message: T) -> None:
        self.msgq.put(message, block=True, timeout=self.timeout)

    def get(self) -> T | None:
        try:
            return self.msgq.get(block=True, timeout=self.timeout)
        except queue.Empty:
            return None


_manager = None


def get_manager() -> multiprocessing.managers.SyncManager:
    global _manager
    if _manager is None:
        _manager = multiprocessing.Manager()
    return _manager


class ManagedMemoryQueue(SyncQueue[T]):
    def __init__(self, maxsize: int = 0, timeout: float = 5.0):
        self.msgq = get_manager().Queue(maxsize=maxsize)
        self.timeout = timeout

    def put(self, message: T) -> None:
        self.msgq.put(message, block=True, timeout=self.timeout)

    def get(self) -> T | None:
        try:
            return self.msgq.get(block=True, timeout=self.timeout)
        except queue.Empty:
            return None


class AsyncioQueue(AsyncQueue[T]):
    def __init__(self, maxsize: int = 0, timeout: float = 5.0):
        self.msgq = asyncio.Queue(maxsize=maxsize)
        self.timeout = timeout

    async def put(self, message: T) -> None:
        await asyncio.wait_for(self.msgq.put(message), timeout=self.timeout)

    async def get(self) -> T | None:
        try:
            return await asyncio.wait_for(self.msgq.get(), timeout=self.timeout)
        except TimeoutError:
            return None
