import abc
import multiprocessing
import multiprocessing.managers
import queue

from imap_tools.message import MailMessage

from jbmailbot.config import ConcurrencyType, MessageQueueType, QueueConfig


class MailQueueBase(abc.ABC):
    @abc.abstractmethod
    def is_thread_safe(self) -> bool:
        pass

    @abc.abstractmethod
    def is_process_safe(self) -> bool:
        pass

    @abc.abstractmethod
    def put(self, message: MailMessage) -> None:
        pass

    @abc.abstractmethod
    def get(self, block: bool = True, timeout: float | None = None) -> MailMessage | None:
        pass


class MailQueue(MailQueueBase):
    def __init__(self, maxsize: int = 0):
        self.msgq = queue.Queue(maxsize=maxsize)

    def is_thread_safe(self) -> bool:
        return True

    def is_process_safe(self) -> bool:
        return False

    def put(self, message: MailMessage) -> None:
        self.msgq.put(message)

    def get(self, block: bool = True, timeout: float | None = None) -> MailMessage | None:
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


class ManagedMailQueue(MailQueue):
    def __init__(self, maxsize: int = 0):
        self.msgq = get_manager().Queue()

    def is_thread_safe(self) -> bool:
        return True

    def is_process_safe(self) -> bool:
        return True

    def put(self, message: MailMessage) -> None:
        self.msgq.put(message)

    def get(self, block: bool = True, timeout: float | None = None) -> MailMessage | None:
        try:
            return self.msgq.get(block=block, timeout=timeout)
        except queue.Empty:
            return None


DEFAULT_QUEUE_TYPE = {
    ConcurrencyType.THREAD: MessageQueueType.THREAD,
    ConcurrencyType.PROCESS: MessageQueueType.PROCESS,
}


def make_mail_queue(config: QueueConfig, worker_type: ConcurrencyType) -> MailQueue:
    queue_type = config.queue_type or DEFAULT_QUEUE_TYPE[worker_type]
    if queue_type == MessageQueueType.THREAD:
        return MailQueue(**config.parameters)
    elif queue_type == MessageQueueType.PROCESS:
        return ManagedMailQueue(**config.parameters)
    else:
        raise ValueError(f"Unknown queue type: {queue_type}")
