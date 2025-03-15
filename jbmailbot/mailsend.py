import abc

from jbmailbot.config import MailSendConfig


class MailSender(abc.ABC):
    @abc.abstractmethod
    def send(self, message: str) -> None:
        pass


class StdoutFakeMailSender(MailSender):
    def send(self, message: str) -> None:
        print(message)


def make_mail_sender(_config: MailSendConfig) -> MailSender:
    return StdoutFakeMailSender()
