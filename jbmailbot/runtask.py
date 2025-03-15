from __future__ import annotations

import abc
import asyncio
import time
from concurrent.futures import Executor, ProcessPoolExecutor, ThreadPoolExecutor
from typing import Generic, TypeVar

from loguru import logger

from jbmailbot.config import ConcurrencyType, WorkerConfig

_last_task_id = 0


def get_next_task_id():
    global _last_task_id
    _last_task_id += 1
    return _last_task_id


def default_task_name(obj: object) -> str:
    return f"Task<{get_next_task_id()}, {obj.__class__.__name__}>"


T = TypeVar("T")


class TaskDone(Generic[T]):
    """Signal that a task is done and should not be rescheduled."""

    def __init__(self, result: T | None = None):
        self.result = result


class Task(abc.ABC, Generic[T]):
    def __init__(self, name: str | None = None):
        self.name = name or default_task_name(self)

    def on_task_exception(self, exc: Exception):
        """
        Called when an exception occurs during task execution.

        By default, this method logs the exception and re-raises it,
        which will stop the task execution. Subclasses can override
        this method to provide custom exception handling (e.g., to catch
        specific exceptions while letting others propagate).

        Args:
            exc: The exception that was raised
        """
        logger.exception(f"Exception in task {self.name}", exc_info=exc)
        raise exc

    def on_task_cancelled(self):
        """
        Called when the task is cancelled.

        This method is called when the task receives a CancelledError,
        which typically happens when cancel() is called. Subclasses can
        override this method to perform custom cleanup operations.

        By default, this method just logs that the task was cancelled.
        """
        logger.debug(f"Task {self.name} received asyncio.CancelledError")


class SyncTask(Task[T]):
    """
    SyncTask represents a task that can be run synchronously,
    or in a thread or process pool.

    Subclasses must implement the run method to define the task's behavior.

    Optionally, subclasses can override on_task_exception and on_task_cancelled
    to provide custom exception handling and cleanup operations.
    """

    @abc.abstractmethod
    def run(self) -> TaskDone[T] | None:
        pass

    def runner(self, executor: Executor | None = None) -> SyncTaskRunner[T]:
        return SyncTaskRunner(self, executor)


class AsyncTask(Task[T]):
    """
    AsyncTask represents a task that can be run asynchronously.

    Subclasses must implement the run method to define the task's behavior.

    Optionally, subclasses can override on_task_exception and on_task_cancelled
    to provide custom exception handling and cleanup operations.
    """

    @abc.abstractmethod
    async def run(self) -> TaskDone[T] | None:
        pass

    def runner(self) -> AsyncTaskRunner[T]:
        return AsyncTaskRunner(self)


class TaskRunner(abc.ABC, Generic[T]):
    """
    TaskRunner is the base class for task runners. Task runners handle running
    a task indefinitely in a loop, or at defined intervals.

    See SyncTaskRunner and AsyncTaskRunner for concrete implementations.
    """

    def __init__(self, task: Task[T]):
        self.running_task: asyncio.Task | None = None
        self.task = task

    @abc.abstractmethod
    async def _run_async(self) -> TaskDone[T] | None:
        pass

    async def run_forever(self, interval: int | None = None) -> T | None:
        """
        Run the task indefinitely in a loop.

        The task will run until one of the following happens:
        1. The run method returns a final result wrapped in TaskDone
        2. The run method raises an exception that isn't handled by on_task_exception
        3. The task is cancelled

        Args:
            interval: minimum seconds between task executions (default: None)
        """
        try:
            while True:
                start_time = time.time()
                try:
                    task_result = await self._run_async()
                    if isinstance(task_result, TaskDone):
                        result = task_result.result
                        logger.info(f"Task {self.task.name} completed gracefully")
                        return result
                except Exception as e:
                    self.task.on_task_exception(e)

                if interval:
                    until_next_call = start_time + interval - time.time()
                    if until_next_call > 0.0:
                        await asyncio.sleep(until_next_call)

        except asyncio.CancelledError:
            self.task.on_task_cancelled()
            return None

    def start(self, interval: int | None = None):
        """
        Start the task, running it indefinitely in a loop.

        Args:
            interval: minimum seconds between task executions (default: None)
        """
        if self.running_task:
            raise RuntimeError(f"{self.__class__.__name__} is already running")

        logger.info("Start running task {} with interval={}", self.task.name, interval)
        self.running_task = asyncio.create_task(self.run_forever(interval), name=self.task.name)

    def cancel(self):
        """
        Cancel the task.
        """
        if not self.running_task:
            raise RuntimeError(f"{self.__class__.__name__} is not running")

        logger.info(f"Cancelling task {self.task.name}")
        self.running_task.cancel()

    async def wait(self):
        if not self.running_task:
            raise RuntimeError(f"{self.__class__.__name__} is not running")

        # Exceptions raised by self.run are already handled by on_task_exception
        # If an exception was raised outside of self.run, something really
        # unexpected happened, so just let the exception propagate
        try:
            res = await self.running_task
        except asyncio.CancelledError:
            res = None
        finally:
            self.running_task = None
        return res

    async def shutdown(self):
        if not self.running_task:
            raise RuntimeError(f"{self.__class__.__name__} is not running")

        self.cancel()
        await self.wait()


class AsyncTaskRunner(TaskRunner[T]):
    """
    AsyncTaskRunner runs an asynchronous task indefinitely, or at defined
    intervals.
    """

    def __init__(self, task: AsyncTask[T]):
        self.running_task: asyncio.Task | None = None
        self.task = task

    async def _run_async(self) -> TaskDone[T] | None:
        return await self.task.run()


class SyncTaskRunner(AsyncTaskRunner[T]):
    """
    SyncTaskRunner runs a blocking task indefinitely, or at defined
    intervals, using an executor (ThreadPoolExecutor or ProcessPoolExecutor).

    When executor is None, the event loop's default executor is used,
    which is a ThreadPoolExecutor, unless it is changed by calling
    loop.set_default_executor.

    When using a ThreadPoolExecutor, the implementation of SyncTask.run
    should be thread-safe (e.g. modifications to non-thread-safe objects
    should be protected by locks).

    Due to the GIL, CPU-bound tasks still block other tasks even when
    run in a different thread. CPU-bound tasks are better run with
    ProcessPoolExecutor.
    """

    def __init__(self, task: SyncTask[T], executor: Executor | None = None):
        self.executor = executor
        self.task = task
        self.running_task: asyncio.Task | None = None

    async def _run_async(self) -> TaskDone[T] | None:
        """
        Execute the blocking run method in the executor.

        This method overrides the parent class method to run the synchronous
        run method in the specified executor (or the default event loop executor
        if None was provided). It returns whatever the run method returns,
        which could be a TaskDone instance to signal completion.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self.task.run)


EXECUTOR_CLASSES = {
    ConcurrencyType.THREAD: ThreadPoolExecutor,
    ConcurrencyType.PROCESS: ProcessPoolExecutor,
}


def make_executor(config: WorkerConfig) -> Executor:
    return EXECUTOR_CLASSES[config.concurrency_type](config.count)
