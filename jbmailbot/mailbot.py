import abc
import asyncio
import queue
from dataclasses import dataclass

from imap_tools.message import MailMessage
from loguru import logger

from jbmailbot.config import MailBotConfig
from jbmailbot.mailqueue import AnyQueue
from jbmailbot.mailsend import MailSender
from jbmailbot.runtask import AsyncTask, TaskDone


@dataclass
class Message:
    sender: str
    content: str


def get_email_plaintext(message: MailMessage, max_body_length: int = 5000) -> str:
    sender = message.from_
    subject = message.subject
    text = message.text
    return f"From: {sender}\nSubject: {subject}\n{text[:max_body_length]}"


def quote_previous_email(message: MailMessage, reply: str) -> str:
    quote_title = f"{message.from_} said at {message.date.isoformat()}:"
    quoted_message = "> " + "\n> ".join(message.text.splitlines())
    return f"{reply}\n\n{quote_title}\n\n{quoted_message}"


class MailBot(abc.ABC):
    @abc.abstractmethod
    async def compose_reply(self, conversation: str) -> str:
        pass

    async def reply(self, message: MailMessage) -> str:
        conversation = get_email_plaintext(message)
        reply = await self.compose_reply(conversation)
        return quote_previous_email(message, reply)


class HelloMailBot(MailBot):
    def __init__(self, name: str):
        self.name = name

    async def compose_reply(self, conversation: str) -> str:
        await asyncio.sleep(5)
        return f"{self.name} says: Hello!"


def make_mailbot(config: MailBotConfig) -> MailBot:
    return HelloMailBot(config.name)


class RunBotTask(AsyncTask[None]):
    def __init__(
        self, mailbot: MailBot, queue: AnyQueue[MailMessage], sender: MailSender, retries: int = 3
    ):
        self.mailbot = mailbot
        self.mailq = queue
        self.sender = sender
        self.retries = retries
        super().__init__()

    def on_task_exception(self, exc: Exception):
        logger.exception(f"Exception in bot runner task {self.name}", exc_info=exc)

    async def run(self) -> TaskDone | None:
        # Set a timeout to avoid blocking indefinitely when trying to shutdown
        try:
            logger.debug("Waiting for message in mail queue with timeout=5")
            message = await asyncio.to_thread(self.mailq.get, block=True, timeout=5)
        except queue.Empty:
            logger.debug("Mail queue is empty")
            message = None
        if message:
            logger.debug(
                "Processing message uid={} id={} from {}",
                message.uid,
                message.obj.get("Message-Id"),
                message.from_,
            )
            for retry_num in range(self.retries + 1):
                try:
                    reply = await self.mailbot.reply(message)
                    self.sender.send(reply)
                    break
                except Exception:
                    logger.exception(
                        "Exception replying to message {} (retry {} of {})",
                        message.uid,
                        retry_num,
                        self.retries,
                    )
