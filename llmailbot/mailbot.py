import abc
import asyncio
import time
from typing import Any, Iterable

from imap_tools.utils import EmailAddress
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from llmailbot.config import ModelSpec, ReplyConfig
from llmailbot.email.model import IMAPMessage, IMAPRawMessage, SimpleEmailMessage
from llmailbot.queue import AsyncQueue
from llmailbot.taskrun import AsyncTask, TaskDone


def quoted(txt: str) -> str:
    return "> " + "\n> ".join(txt.splitlines())


def quote_email(email: IMAPMessage) -> str:
    quote_title = f"{email.addr_from.name or email.addr_from.email} said"
    if email.date:
        quote_title += f" at {email.date.strftime('%Y-%m-%d %H:%M')}:"
    return f"{quote_title}\n\n{quoted(email.text)}"


class MailBot(abc.ABC):
    """
    MailBot is the interface class for mailbots.
    """

    @abc.abstractmethod
    async def compose_reply(
        self,
        spec: ModelSpec,
        bot_email: str,
        user_email: str,
        conversation: str,
    ) -> str:
        pass

    def __init__(self, specs: list[ModelSpec]):
        self.specs = specs

    def _get_spec(self, to_addrs: list[str]) -> tuple[str, ModelSpec] | tuple[None, None]:
        for addr in to_addrs:
            for spec in self.specs:
                if spec._address_regex is not None:
                    if spec._address_regex.match(addr):
                        return addr, spec
                else:
                    if spec.address == addr:
                        return addr, spec

        logger.warning("Received email for address with no matching configuration: {}", to_addrs)
        return None, None

    async def reply(self, email: IMAPMessage) -> SimpleEmailMessage | None:
        bot_email, spec = self._get_spec([a.email for a in email.addrs_to])
        if spec is None or bot_email is None:
            return None
        conversation = str(email)
        reply_body = await self.compose_reply(spec, bot_email, email.addr_from.email, conversation)
        reply_body = reply_body + "\n\n" + quote_email(email)
        return email.create_reply(EmailAddress(spec.name, bot_email), reply_body)


class HelloMailBot(MailBot):
    """
    HelloMailBot is a test MailBot implementation that generates a simple hardcoded reply.
    """

    async def compose_reply(
        self,
        spec: ModelSpec,
        bot_email: str,
        user_email: str,
        conversation: str,
    ) -> str:
        await asyncio.sleep(3)
        return f"Hello! My name is {spec.name}. I'm not very smart yet."


DEFAULT_CONFIGURABLE_FIELDS = frozenset(
    {
        "model",
        "model_provider",
        "max_tokens",
        "temperature",
    }
)


class LangChainMailBot(MailBot):
    """
    LangChainMailBot is a MailBot implementation that generates LLM replies,
    using langchain chat models.

    It can reply on behalf of any number of "bots" by choosing a configuration
    based on the email To header.
    """

    def __init__(
        self,
        specs: list[ModelSpec],
        configurable_fields: Iterable[str] | None = None,
    ):
        super().__init__(specs)
        self.configurable_fields = set(configurable_fields or DEFAULT_CONFIGURABLE_FIELDS)
        self.chat_model = init_chat_model(
            max_retries=3,
            timeout=10,
            configurable_fields=list(self.configurable_fields),
        )

    def _build_system_prompt(self, spec: ModelSpec, bot_email: str, user_email: str) -> str:
        return spec.system_prompt.format(
            name=spec.name,
            bot_email=bot_email,
            user_email=user_email,
        )

    def _get_chat_model_config(self, spec: ModelSpec, bot_email: str) -> dict[str, Any]:
        model_config = {}
        for k, v in spec.chat_model_config(bot_email).items():
            k = k.lower()
            if k in self.configurable_fields:
                model_config[k] = v
            else:
                logger.warning("Model config field {} was provided but is not configurable", k)

        return model_config

    async def compose_reply(
        self,
        spec: ModelSpec,
        bot_email: str,
        user_email: str,
        conversation: str,
    ) -> str:
        system_prompt = self._build_system_prompt(spec, bot_email, user_email)
        model_config = self._get_chat_model_config(spec, bot_email)
        truncated_msg = conversation[: spec.max_input_length]
        logger.debug(
            "Composing reply with config={}, prompt={}, message length={}",
            model_config,
            system_prompt,
            len(truncated_msg),
        )
        messages = [SystemMessage(system_prompt), HumanMessage(truncated_msg)]
        try:
            stime = time.time()
            chat_model = self.chat_model.with_config(**model_config)
            response = await chat_model.ainvoke(messages)
            logger.debug(
                "{} {} response time: {}",
                spec.name,
                model_config["model"],
                time.time() - stime,
            )
            if isinstance(response.content, str):
                return response.content
            else:
                raise ValueError(f"Expected a str response, got: {repr(response.content)}")
        except Exception as e:
            logger.error("Chat model error: {}", e)
            return "We apologize, there was a system error. Your email is lost forever :("


def make_mailbot(
    specs: list[ModelSpec],
    configurable_fields: Iterable[str] | None = None,
    hello_bot: bool = False,
) -> MailBot:
    if hello_bot:
        return HelloMailBot(specs)
    else:
        return LangChainMailBot(specs, configurable_fields)


class BotReplyTask(AsyncTask[None]):
    """
    BotReplyTask is a task that runs a mailbot to reply to a single email.

    Args:
        mailbot: The mailbot instance to run
        email: The user email being replied to
        send_queue: The outgoing email queue
        retries: Number of retries on failure
        queue_timeout: Timeout for queue operations in seconds (high value hangs on exit)
    """

    def __init__(
        self,
        mailbot: MailBot,
        email: IMAPMessage,
        send_queue: AsyncQueue[SimpleEmailMessage],
        retries: int = 3,
    ):
        super().__init__(f"{self.__class__.__name__}<{mailbot.__class__.__name__}>")
        self.name = self._name
        self.mailbot = mailbot
        self.email = email
        self.sendq = send_queue
        self.retries = retries

    async def qput(self, message: SimpleEmailMessage) -> None:
        logger.trace(
            "Putting reply in mail queue",
        )
        await self.sendq.put(message)

    async def run(self) -> TaskDone[None] | None:
        email = self.email
        # TODO: implement retry logic in TaskRunner
        for retry_num in range(self.retries + 1):
            try:
                logger.info(
                    "{} generating reply to {}",
                    self.name,
                    email.summary(),
                )
                reply = await self.mailbot.reply(email)
                if reply is not None:
                    await self.qput(reply)
                break
            except Exception:
                logger.exception(
                    "Exception replying to email {} (retry {} of {})",
                    email.summary(),
                    retry_num,
                    self.retries,
                )
        return TaskDone(None)


class BotReplySpawnTask(AsyncTask[None]):
    """
    BotReplySpawnTask creates and runs a BotReplyTask for each email
    received from the incoming email queue.

    Args:
        mailbot: The mailbot instance to run
        recv_queue: Incoming email queue
        send_queue: Outgoing email queue
        retries: Number of retries on failure for reply task (default: 3)
        one_at_a_time: If True, will only spawn one reply task at a time (default: False)
        instance_n: Instance number for logging (default: None)
    """

    def __init__(
        self,
        mailbot: MailBot,
        recv_queue: AsyncQueue[IMAPRawMessage],
        send_queue: AsyncQueue[SimpleEmailMessage],
        retries: int = 3,
        one_at_a_time: bool = False,
        instance_n: int | None = None,
    ):
        self.mailbot = mailbot
        self.recvq = recv_queue
        self.sendq = send_queue
        self.retries = retries
        self.one_at_a_time = one_at_a_time
        self.name = f"{self.__class__.__name__}<{mailbot.__class__.__name__}>"
        if instance_n is not None:
            self.name += f".{instance_n}"
        super().__init__(self.name)

    async def run(self) -> TaskDone | None:
        logger.trace("Waiting for message in mail queue")
        email = await self.recvq.get()
        if not email:
            logger.trace("No message in mail queue")
            return

        reply_task = BotReplyTask(
            mailbot=self.mailbot,
            email=email.parsed(),
            send_queue=self.sendq,
            retries=self.retries,
        )
        reply_runner = reply_task.runner()
        reply_runner.start()
        if self.one_at_a_time:
            await reply_runner.wait()


def make_bot_reply_spawn_task(
    config: ReplyConfig,
    recv_queue: AsyncQueue[IMAPRawMessage],
    send_queue: AsyncQueue[SimpleEmailMessage],
):
    return BotReplySpawnTask(
        make_mailbot(
            config.models,
            configurable_fields=config.chat_model_configurable_fields,
        ),
        recv_queue=recv_queue,
        send_queue=send_queue,
    )
