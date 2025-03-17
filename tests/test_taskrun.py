import asyncio
import time
from unittest.mock import MagicMock

import pytest

from llmailbot.taskrun import (
    AsyncTask,
    StoppedError,
    TaskDone,
)


class SleepTask(AsyncTask[int]):
    """A simple task that sleeps for a specified duration and returns a value."""

    def __init__(self, sleep_time: float, return_value: int, name: str | None = None):
        super().__init__(name=name)
        self.sleep_time = sleep_time
        self.return_value = return_value
        self.run_count = 0

    async def run(self) -> TaskDone[int] | None:
        self.run_count += 1
        await asyncio.sleep(self.sleep_time)
        return TaskDone(self.return_value)


class InfiniteTask(AsyncTask[None]):
    """A task that runs indefinitely until stopped or cancelled."""

    def __init__(self, name: str | None = None):
        super().__init__(name=name)
        self.run_count = 0

    async def run(self) -> TaskDone[None] | None:
        self.run_count += 1
        await asyncio.sleep(0.1)
        return None  # Continue running


class CounterTask(AsyncTask[int]):
    """A task that counts up to a target value and then returns."""

    def __init__(self, target: int, name: str | None = None):
        super().__init__(name=name)
        self.count = 0
        self.target = target

    async def run(self) -> TaskDone[int] | None:
        self.count += 1
        if self.count >= self.target:
            return TaskDone(self.count)
        await asyncio.sleep(0.1)
        return None  # Continue running


class ErrorTask(AsyncTask[None]):
    """A task that raises an exception after a specified number of runs."""

    def __init__(
        self, error_on_run: int, exception: Exception | None = None, name: str | None = None
    ):
        super().__init__(name=name)
        self.run_count = 0
        self.error_on_run = error_on_run
        self.exception = exception or ValueError("Test error")
        self.handle_exception_called = False

    async def run(self) -> TaskDone[None] | None:
        self.run_count += 1
        if self.run_count >= self.error_on_run:
            raise self.exception
        await asyncio.sleep(0.1)
        return None

    def handle_exception(self, exc: Exception):
        self.handle_exception_called = True
        # Re-raise to stop the task
        raise exc


@pytest.mark.asyncio
async def test_task_result():
    """Test that a task returns the expected result."""
    task = SleepTask(0.1, 42)
    runner = task.runner()
    runner.start()

    result = await runner.result()
    assert result == 42
    assert task.run_count == 1


@pytest.mark.asyncio
async def test_task_wait():
    """Test that wait() waits for the task to complete without returning a result."""
    task = SleepTask(0.1, 42)
    runner = task.runner()
    runner.start()

    await runner.wait()
    assert task.run_count == 1
    assert runner.done is not None
    assert runner.done.result == 42


@pytest.mark.asyncio
async def test_task_stop():
    """Test that stopping a task prevents future runs but allows the current run to complete."""
    task = InfiniteTask()
    runner = task.runner()
    runner.start(interval=0.1)

    # Let it run a few times
    await asyncio.sleep(0.3)
    initial_count = task.run_count
    assert initial_count > 0

    # Stop the task
    runner.stop()

    # Wait for it to finish
    with pytest.raises(StoppedError):
        await runner.result()

    # Verify it didn't run again after being stopped
    assert task.run_count == initial_count


@pytest.mark.asyncio
async def test_task_cancel():
    """Test that cancelling a task interrupts it immediately."""
    task = SleepTask(1.0, 42)  # Long sleep
    runner = task.runner()
    runner.start()

    # Cancel immediately
    await asyncio.sleep(0.1)  # Give it time to start
    runner.cancel()

    # Verify it was cancelled
    with pytest.raises(asyncio.CancelledError):
        await runner.result()

    assert task.run_count == 1  # It started but didn't complete


@pytest.mark.asyncio
async def test_task_with_interval():
    """Test that a task respects the interval between runs."""
    task = CounterTask(3)
    start_time = time.time()
    runner = task.runner()
    runner.start(interval=0.2)  # 0.2 seconds between runs

    result = await runner.result()
    end_time = time.time()

    assert result == 3
    assert task.count == 3

    # Should take at least 0.4 seconds (2 intervals)
    assert end_time - start_time >= 0.4


@pytest.mark.asyncio
async def test_task_error_handling():
    """Test that task errors are handled properly."""
    task = ErrorTask(2)
    runner = task.runner()
    runner.start()

    # The task should raise an error on the second run
    with pytest.raises(ValueError, match="Test error"):
        await runner.result()

    assert task.run_count == 2
    assert task.handle_exception_called


@pytest.mark.asyncio
async def test_multiple_runners_same_task():
    """Test that the same task can have multiple runners."""
    task = SleepTask(0.1, 42)

    runner1 = task.runner()
    runner2 = task.runner()

    runner1.start()
    runner2.start()

    result1 = await runner1.result()
    result2 = await runner2.result()

    assert result1 == 42
    assert result2 == 42
    assert task.run_count == 2  # The task ran twice


@pytest.mark.asyncio
async def test_task_is_ongoing():
    """Test the is_ongoing property."""
    task = SleepTask(0.2, 42)
    runner = task.runner()

    # Not started yet
    assert runner.is_not_finished

    # Started but not done
    runner.start()
    assert runner.is_not_finished

    # Wait for completion
    await runner.result()
    assert not runner.is_not_finished


@pytest.mark.asyncio
async def test_task_on_cancelled():
    """Test that on_cancelled is called when a task is cancelled."""
    task = SleepTask(0.5, 42)
    task.on_cancelled = MagicMock()

    runner = task.runner()
    runner.start()

    await asyncio.sleep(0.1)
    runner.cancel()

    try:
        await runner.result()
    except asyncio.CancelledError:
        pass

    task.on_cancelled.assert_called_once()


@pytest.mark.asyncio
async def test_task_on_stopped():
    """Test that on_stopped is called when a task is stopped."""
    task = InfiniteTask()
    task.on_stopped = MagicMock()

    runner = task.runner()
    runner.start()

    await asyncio.sleep(0.1)
    runner.stop()

    try:
        await runner.result()
    except StoppedError:
        pass

    task.on_stopped.assert_called_once()
