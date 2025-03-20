"""
Task and TaskRunner are used to define and run sync and async tasks.

Tasks are defined by subclassing SyncTask or AsyncTask and overriding the run method.
TaskRunners manage the execution of the tasks.

A TaskRunner executes the run method of its Task one or more times,
until one of the following occurs:
 - the task signals completion by returning TaskDone
 - the task is cancelled or stopped
 - an exception is raised and not caught by Task.handle_exception

Below are some examples for defining tasks with common execution patterns.

A one-shot task returns TaskDone immediately (but this should just be a function):
>>> class OneShotTask(AsyncTask[int]):
...     async def run(self) -> TaskDone[int]:
...         await asyncio.sleep(5)
...         return TaskDone(42)
>>>
>>> res = await OneShotTask().runner().start().result()

A long-lived "worker" task never returns TaskDone:
>>> class WorkerTask(AsyncTask[int]):
...     async def run(self) -> TaskDone[None]:
...         task = await self.task_queue.get()
...         result = self.do_some_work(task)
...         await self.result_queue.put(result)
>>>
>>> WorkerTask().runner().start()

A periodic task never returns TaskDone, and is started with an interval:
>>> class PeriodicTask(AsyncTask[int]):
...     async def run(self) -> TaskDone[None]:
...         print(f"The time is now: {time.time()}")
>>>
>>> PeriodicTask().runner().start(interval=1)

An iterative task returns TaskDone when its result is ready
>>> class IterativeTask(AsyncTask[int]):
...     async def run(self) -> TaskDone[int]:
...         self.count += 1
...         if self.count >= 5:
...             return TaskDone(self.count)
>>>
>>> task = IterativeTask().runner().start(interval=1)
>>> res = await task.result()

SyncTasks are run asynchronously using a ThreadPoolExecutor or ProcessPoolExecutor,
while AsyncTasks are run directly in asyncio.

Although you should probably just use asyncio.Task, this module adds a couple of things on top:
- TaskRunner tries to paper over the differences between sync and async units of work,
  though when running sync tasks you must still pay attention to thread/process-safety and the GIL
- As an alternative to cancel(), TaskRunner provides a stop() method, which acts as a soft-cancel.
  It lets the current Task.run() call finish before cancelling. For some tasks it makes it
  easier to reason about the task's lifecycle, compared to cancel(), which can
  raise CancelledError anywhere await is used. However stop() is not guaranteed
  to stop a task anytime soon, if it's waiting on I/O that may never come.

Beware that due to the Python GIL, running CPU-bound tasks in a ThreadPoolExecutor
still blocks the entire interpreter. Generally ThreadPoolExecutor is appropriate
for IO-bound tasks, while ProcessPoolExecutor is appropriate for CPU-bound tasks,
but has higher overhead.
"""

from __future__ import annotations

import abc
import asyncio
import datetime
import time
from collections import defaultdict
from concurrent.futures import Executor, ProcessPoolExecutor, ThreadPoolExecutor
from typing import Generic, Self, TypeVar

from loguru import logger
from typing_extensions import Any

from llmailbot.config import WorkerPoolConfig, WorkerType
from llmailbot.ratelimit import LimitResult, RateLimiter

_last_task_id: dict[type, int] = defaultdict(lambda: 0)


def get_next_task_id(cls: type) -> int:
    global _last_task_id
    _last_task_id[cls] += 1
    return _last_task_id[cls]


def default_task_name(obj: object) -> str:
    return f"{obj.__class__.__name__}.{get_next_task_id(obj.__class__)}"


T = TypeVar("T")


class TaskDone(Generic[T]):
    """
    Wrapper for the final result of a task, signalling that it should not be run again.
    """

    def __init__(self, result: T):
        self.result = result


class Task(abc.ABC, Generic[T]):
    def __init__(self, name: str | None = None):
        self._name = name or default_task_name(self)

    @abc.abstractmethod
    def runner(self, executor: Executor | None = None) -> TaskRunner[T]:
        pass

    def handle_exception(self, exc: Exception):
        """
        Called when an exception occurs during task execution.

        If the exception is re-raised, execution will be stopped.
        (The default implementation always re-raises.)

        Args:
            exc: The exception that was raised
        """
        logger.exception("Exception in task {}", self._name, exc_info=exc)
        raise exc

    def on_stopped(self):
        """
        Called after the task is stopped.

        By default, this method calls on_cancelled().
        """
        self.on_cancelled()

    def on_cancelled(self):
        """
        Called after the task is cancelled.

        It is also called when a task is stopped, unless on_stopped is overridden.

        By default, this method just logs that the task was cancelled.
        """
        logger.info("Task {} received asyncio.CancelledError", self._name)


class SyncTask(Task[T]):
    """
    SyncTask represents a task that can be run synchronously,
    or asynchronously in a thread or process pool.

    Subclasses must implement the run method to define the task's behavior.

    Optionally, subclasses can override handle_exception and on_cancelled
    to provide custom exception handling and cleanup operations.
    """

    @abc.abstractmethod
    def run(self) -> TaskDone[T] | None:
        """
        The main task function. Must be overriden by concrete Tasks.
        """
        pass

    def runner(self, executor: Executor | None = None) -> SyncTaskRunner[T]:
        """
        Get runner for this task.

        The same task can have multiple runners, but the task instance will
        be shared between runners.

        Creating multiple runners for the same task instance is only
        recommended for stateless tasks.
        """
        return SyncTaskRunner(self, executor)


class AsyncTask(Task[T]):
    """
    AsyncTask represents a task that can be run asynchronously.

    Subclasses must implement the run method to define the task's behavior.

    Optionally, subclasses can override handle_exception and on_cancelled
    to provide custom exception handling and cleanup operations.
    """

    @abc.abstractmethod
    async def run(self) -> TaskDone[T] | None:
        """
        The main task function. Must be overriden by concrete Tasks.
        """
        pass

    def runner(self, executor: Executor | None = None) -> AsyncTaskRunner[T]:
        """
        Get runner for this task.

        The same task can have multiple runners, but the task instance will
        be shared between runners.

        Creating multiple runners for the same task instance is only
        recommended for stateless tasks.

        The executor parameter has no effect for AsyncTask, the task runs
        with asyncio directly, it is only there to match the signature of
        Task/SyncTask.
        """
        if executor is not None:
            logger.warning("An executor was passed to AsyncTask; it will be ignored")
        return AsyncTaskRunner(self)


STOPPED_MESSAGE = "TaskRunner.STOPPED"


class StoppedError(asyncio.CancelledError):
    def __init__(self):
        super().__init__(STOPPED_MESSAGE)


class TaskRunner(abc.ABC, Generic[T]):
    """
    TaskRunner handles running a Task one or more times, until
    the Task returns a final result wrapped in TaskDone, or is interrupted.

    These are the ways a task can get interrupted:
    - immediately, when an exception is raised and not caught by Task.handle_exception
    - soon, when the task is cancelled
    - eventually, when the task is stopped

    See SyncTaskRunner and AsyncTaskRunner for concrete implementations
    which run SyncTask and AsyncTask respectively.
    """

    def __init__(self, task: Task[T]):
        self.run_until_done_task: asyncio.Task | None = None
        self.task = task
        self.name = f"{default_task_name(self)}<{task._name}>"

        self.done: TaskDone[T] | None = None
        self.stopped: bool = False
        self.cancelled: bool = False
        self.exception: Exception | None = None
        self.waiting_for_interval: bool = False

    @property
    def is_finished(self) -> bool:
        return bool(self.done or self.stopped or self.cancelled or self.exception)

    async def wait_for_interval(self, duration: float):
        self.waiting_for_interval = True
        await asyncio.sleep(duration)
        self.waiting_for_interval = False

    @abc.abstractmethod
    async def _run_task_async(self) -> TaskDone[T] | None:
        pass

    async def _run_once(self) -> None:
        # Should not happen, but just in case
        assert not self.is_finished, f"{self.name} is finished"
        try:
            task_output = await self._run_task_async()
            if isinstance(task_output, TaskDone):
                logger.success("Task {} is done", self.name)
                self.done = task_output

        # asyncio.CancelledError is a subclass of BaseException, not Exception
        # so it is not caught here. it is handled by _run_until_done
        except Exception as exc:
            try:
                self.task.handle_exception(exc)
            except Exception as inner_exc:
                self.exception = exc
                raise inner_exc from exc

    async def _run_until_done(self, interval: float | None = None) -> T:
        try:
            last_call_t = 0.0
            while True:
                if interval:
                    until_next_call_t = last_call_t + interval - time.time()
                    if until_next_call_t > 0.0:
                        logger.trace(
                            "Task {} waiting {:0.5f} seconds until next call",
                            self.name,
                            until_next_call_t,
                        )
                        await self.wait_for_interval(until_next_call_t)

                await self._run_once()
                last_call_t = time.time()

                # Some of these should not happen, but just in case
                if self.done is not None:
                    return self.done.result
                if self.stopped:
                    raise StoppedError()
                if self.cancelled:
                    raise asyncio.CancelledError()
                if self.exception:
                    raise self.exception

        # We don't catch Exception here, it is caught in _run_once
        # If an Exception reaches here it means it was not handled by Task.handle_exception
        # and should be propagated, or it was raised outside of Task.run
        # Task.handle_exception should not be called for an exception that was raised
        # by TaskRunner's own code rather than Task.run
        except asyncio.CancelledError as e:
            if e.args and e.args[0] == STOPPED_MESSAGE:
                self.stopped = True
                self.task.on_stopped()
            else:
                self.cancelled = True
                self.task.on_cancelled()
            raise

    def start(self, interval: float | None = None) -> Self:
        """
        Start the task, running it one or more times until done, cancelled,
        stopped, or interrupted by an unhandled exception.

        Args:
            interval: minimum delay between task executions, in seconds (default: None)
        """
        assert not self.run_until_done_task, f"{self.name} was already started"

        logger.info("Start running task {} with interval={}", self.name, interval)
        self.run_until_done_task = asyncio.create_task(
            self._run_until_done(interval),
            name=self.name,
        )
        return self

    def stop(self):
        """
        Stops future calls to Task.run.
        Waits for Task.run to return if it is currently executing.

        To interrupt Task.run, call TaskRunner.cancel() instead.
        """
        assert self.run_until_done_task and not self.is_finished, f"{self.name} is not ongoing"

        logger.info("Stopping task {}", self.name)
        self.stopped = True
        if self.waiting_for_interval:
            logger.info("Task {} is currently sleeping, cancelling it", self.name)
            self.run_until_done_task.cancel(STOPPED_MESSAGE)

    def cancel(self):
        """
        Cancel the task immediately, interrupting the current execution
        by raising asyncio.CancelledError.
        """
        assert self.run_until_done_task and not self.is_finished, f"{self.name} is not ongoing"

        logger.info("Cancelling task {}", self.name)
        self.cancelled = True
        self.run_until_done_task.cancel()

    async def shutdown(self, deadline: int | None = None):
        """
        Stop the task and wait for it to finish.

        Args:
            deadline: maximum time to wait for the task to finish, in seconds
                after which the task will be cancelled (default: None)
        """
        self.stop()
        if deadline is not None:
            try:
                await asyncio.wait_for(self.wait(), timeout=deadline)
            except asyncio.TimeoutError:
                self.cancel()
                await self.wait()
        else:
            await self.wait()

    async def result(self) -> T:
        """
        Wait and get result of the task, or raises exceptions, including
        asyncio.CancelledError.
        """
        assert self.run_until_done_task, f"{self.name} was not started"
        return await self.run_until_done_task

    async def wait(self) -> None:
        """
        Wait for the task to finish. Does not return result or raise.
        """
        assert self.run_until_done_task, f"{self.name} was not started"
        try:
            await self.run_until_done_task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass


class AsyncTaskRunner(TaskRunner[T]):
    """
    AsyncTaskRunner runs an AsyncTask.

    See documentation for TaskRunner for more details on the TaskRunner interface.
    """

    def __init__(self, task: AsyncTask[T]):
        super().__init__(task)
        self.task = task

    async def _run_task_async(self) -> TaskDone[T] | None:
        return await self.task.run()


class SyncTaskRunner(TaskRunner[T]):
    """
    SyncTaskRunner runs a blocking SyncTask asynchronously,
    using a concurrent.futures Executor.

    See documentation for TaskRunner for more details on the TaskRunner interface.

    If executor is not passed in, the event loop's default executor is used,
    which is normally a ThreadPoolExecutor.

    The loop's default executor can be changed by calling loop.set_default_executor.

    Depending on the type of executor used, the implementation of SyncTask.run
    must be thread-safe or process-safe.

    Due to the GIL, CPU-bound tasks block the event loop when run in a thread pool.
    """

    def __init__(self, task: SyncTask[T], executor: Executor | None = None):
        super().__init__(task)
        self.task = task
        self.executor = executor

    async def _run_task_async(self) -> TaskDone[T] | None:
        """
        Execute the blocking SyncTask.run method asynchronously by
        using the runner's executor.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self.task.run)


async def run_in_background(
    task: Task[T],
    interval: float | None = None,
    restart_delay: int = 1,
    max_repeated_exc: int | None = 3,
    max_repeated_exc_period: int = 10,
    logger: Any = None,
) -> None:
    """
    Helper to run a task asynchronously in the background.

    Args:
        task: The task to run (SyncTask or AsyncTask).
        interval: Minimum delay between task executions, in seconds (default: None)
        restart_delay: Delay between restarts, in seconds (default: 1)
        max_repeated_exc: Max number of the same exception within the max_repeated_exc_period
            before giving up (default: 3).
        max_repeated_exc_period: Max time in seconds for same-error error limit
            before giving up (default: 10).
        logger: Logger to use for logging (default: None)
    """

    def log(lvl: str, msg: str, *args, **kwargs):
        if logger:
            logger.log(lvl, msg, *args, **kwargs)

    exc_limits = None
    if max_repeated_exc:
        exc_period_td = datetime.timedelta(seconds=max_repeated_exc_period)
        exc_limits = defaultdict(lambda: RateLimiter(exc_period_td, max_repeated_exc))

    while True:
        try:
            log("INFO", "Task {} is starting", task._name)
            await task.runner().start(interval).result()
        except Exception as exc:
            if exc_limits is None:
                continue

            rate_limit_res = exc_limits[type(exc)].count()
            if rate_limit_res == LimitResult.EXCEEDED:
                log(
                    "ERROR",
                    "Task {} failed too many times due to {}",
                    task._name,
                    type(exc),
                )
                raise exc

            await asyncio.sleep(restart_delay)
        else:
            log("SUCCESS", "Task {} is done; exiting", task._name)


EXECUTOR_CLASSES = {
    WorkerType.THREAD: ThreadPoolExecutor,
    WorkerType.PROCESS: ProcessPoolExecutor,
}


def make_executor(config: WorkerPoolConfig) -> Executor:
    return EXECUTOR_CLASSES[config.worker_type](config.count)
