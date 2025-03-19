import abc
import asyncio
from typing import Generic, TypeVar

T = TypeVar("T")


class SyncQueue(abc.ABC, Generic[T]):
    @abc.abstractmethod
    def put(self, message: T) -> None:
        pass

    @abc.abstractmethod
    def get(self) -> T | None:
        pass


class AsyncQueue(abc.ABC, Generic[T]):
    @abc.abstractmethod
    async def put(self, message: T) -> None:
        pass

    @abc.abstractmethod
    async def get(self) -> T | None:
        pass


class AsyncAdapter(AsyncQueue[T]):
    def __init__(self, queue: SyncQueue[T]):
        self.queue = queue

    async def put(self, message: T) -> None:
        await asyncio.to_thread(self.queue.put, message)

    async def get(self) -> T | None:
        return await asyncio.to_thread(self.queue.get)


def to_async_queue(q: SyncQueue[T] | AsyncQueue[T]) -> AsyncQueue[T]:
    if isinstance(q, AsyncQueue):
        return q
    return AsyncAdapter(q)
