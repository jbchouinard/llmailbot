import asyncio
import pickle
from typing import Awaitable, Callable, cast

from loguru import logger

from llmailbot.config import RedisConfig

from .core import AsyncQueue, SyncQueue, T

try:
    import redis
    import redis.asyncio as aioredis
except ImportError as e:
    raise ImportError(
        "redis is required for Redis queue; install it with "
        "'poetry install --extras redis' or pip install llmailbot[redis]"
    ) from e


type Serialize[T] = Callable[[T], bytes]
type Deserialize[T] = Callable[[bytes], T]


class AsyncRedisQueue(AsyncQueue[T]):
    def __init__(
        self,
        conf: RedisConfig,
        key: str,
        timeout: int = 5,
        serialize: Serialize[T] = pickle.dumps,
        deserialize: Deserialize[T] = pickle.loads,
    ):
        self.redis = aioredis.Redis(
            host=conf.host,
            port=conf.port,
            db=conf.db,
            username=conf.username,
            password=conf.password,
        )
        self.key = key
        self.serialize = serialize
        self.deserialize = deserialize
        self.timeout = timeout

    async def put(self, message: T) -> None:
        await asyncio.wait_for(
            cast(Awaitable[int], self.redis.lpush(self.key, self.serialize(message))),
            timeout=self.timeout,
        )

    async def get(self) -> T | None:
        vals = await cast(
            Awaitable[list[bytes]], self.redis.brpop([self.key], timeout=self.timeout)
        )
        if not vals:
            return None
        logger.trace("Got {} values from Redis queue", repr([type(val) for val in vals]))
        return self.deserialize(vals[1])


class SyncRedisQueue(SyncQueue[T]):
    def __init__(
        self,
        conf: RedisConfig,
        key: str,
        serialize: Serialize[T] = pickle.dumps,
        deserialize: Deserialize[T] = pickle.loads,
        timeout: int = 5,
    ):
        self.redis = redis.Redis(
            host=conf.host,
            port=conf.port,
            db=conf.db,
            username=conf.username,
            password=conf.password,
        )
        self.key = key
        self.serialize = serialize
        self.deserialize = deserialize
        self.timeout = timeout

    def put(self, message: T) -> None:
        self.redis.lpush(self.key, self.serialize(message))

    def get(self) -> T | None:
        vals = cast(list[bytes], self.redis.brpop([self.key], timeout=self.timeout))
        if not vals:
            return None
        logger.trace("Got {} values from Redis queue", repr([type(val) for val in vals]))
        return self.deserialize(vals[1])
