import abc
import asyncio
from dataclasses import dataclass

from loguru import logger

from jbmailbot.config import MailBotConfig
from jbmailbot.email.model import SimpleEmail
from jbmailbot.queue import AnyQueue
from jbmailbot.runtask import AsyncTask, TaskDone


@dataclass
class Message:
    sender: str
    content: str


def quoted(txt: str) -> str:
    return "> " + "\n> ".join(txt.splitlines())


def quote_email(email: SimpleEmail) -> str:
    quote_title = f"{email.addr_from} said"
    if email.sent_at:
        quote_title += f" at {email.sent_at.strftime('%Y-%m-%d %H:%M')}:"
    return f"{quote_title}\n\n{quoted(email.body)}"


class MailBot(abc.ABC):
    def __init__(self, name: str, send_from: str):
        self.name = name
        self.send_from = send_from

    @abc.abstractmethod
    async def compose_reply(self, conversation: str) -> str:
        pass

    async def reply(self, email: SimpleEmail) -> SimpleEmail | None:
        conversation = str(email)
        reply_body = await self.compose_reply(conversation)
        reply_body = reply_body + "\n\n" + quote_email(email)

        return SimpleEmail.reply(email, self.send_from, reply_body)


class HelloMailBot(MailBot):
    async def compose_reply(self, conversation: str) -> str:
        await asyncio.sleep(3)
        return f"{self.name} says: Hello!"


def make_mailbot(config: MailBotConfig) -> MailBot:
    return HelloMailBot(config.name, config.send.send_from)


class RunBotTask(AsyncTask[None]):
    def __init__(
        self,
        mailbot: MailBot,
        recv_queue: AnyQueue[SimpleEmail],
        send_queue: AnyQueue[SimpleEmail],
        retries: int = 3,
        queue_timeout: int = 5,
    ):
        self.mailbot = mailbot
        self.recvq = recv_queue
        self.sendq = send_queue
        self.retries = retries
        self.queue_timeout = queue_timeout
        super().__init__()

    def on_task_exception(self, exc: Exception):
        logger.exception(f"Exception in bot runner task {self.name}", exc_info=exc)

    async def run(self) -> TaskDone | None:
        # Set a timeout to avoid blocking indefinitely when trying to shutdown
        logger.debug("Waiting for message in mail queue with timeout={}", self.queue_timeout)
        message = await asyncio.to_thread(self.recvq.get, block=True, timeout=self.queue_timeout)
        if message:
            for retry_num in range(self.retries + 1):
                try:
                    logger.info(
                        "{} generating reply to email {}",
                        self.mailbot.name,
                        message.summary(),
                    )
                    reply = await self.mailbot.reply(message)
                    if reply:
                        logger.debug(
                            "Putting reply in mail queue with timeout={}",
                            self.queue_timeout,
                        )
                        await asyncio.to_thread(
                            self.sendq.put, reply, block=True, timeout=self.queue_timeout
                        )
                    break
                except Exception:
                    logger.exception(
                        "Exception replying to email {} (retry {} of {})",
                        message.summary(),
                        retry_num,
                        self.retries,
                    )
