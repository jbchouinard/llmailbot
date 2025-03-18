from __future__ import annotations

import datetime
from dataclasses import dataclass
from email.message import EmailMessage, Message

from imap_tools.message import MailMessage
from imap_tools.utils import EmailAddress

from llmailbot.queue import AnyQueue


@dataclass
class SimpleEmail:
    """
    SimpleEmail represents a simple (plain text) email message.
    """

    addr_from: EmailAddress
    addr_to: tuple[EmailAddress, ...]
    subject: str
    body: str
    sent_at: datetime.datetime | None = None
    message_uid: str | None = None
    message_id: str | None = None
    in_reply_to: str | None = None
    references: str | None = None
    parsed_message: Message | None = None
    raw_message_data: bytes | None = None

    def __str__(self) -> str:
        from_str = self.addr_from.full
        to_str = ", ".join([a.full for a in self.addr_to])
        return f"From: {from_str}\nTo: {to_str}\nSubject: {self.subject}\n{self.body}"

    def summary(self) -> str:
        return (
            f"Email From: {self.addr_from.email} To: {','.join([a.email for a in self.addr_to])} "
            f"Date: {self.sent_at} UID: {self.message_uid} ID: {self.message_id}"
        )

    @classmethod
    def from_message(cls, message: MailMessage) -> SimpleEmail:
        if not message.from_values:
            raise ValueError("Message must have a From address")
        return cls(
            addr_from=message.from_values,
            addr_to=message.to_values,
            subject=message.subject,
            body=message.text,
            sent_at=message.date,
            message_uid=message.uid,
            message_id=message.obj.get("Message-Id"),
            in_reply_to=message.obj.get("In-Reply-To"),
            references=message.obj.get("References"),
            parsed_message=message.obj,
            raw_message_data=message._raw_message_data,  # pyright: ignore[reportAttributeAccessIssue]
        )

    @classmethod
    def reply(cls, email: SimpleEmail, addr_from: EmailAddress, body: str) -> SimpleEmail:
        return cls(
            addr_from=addr_from,
            addr_to=(email.addr_from,),
            subject=f"Re: {email.subject}",
            body=body,
            in_reply_to=email.message_id,
            references=email.references,
        )

    def to_email_message(self) -> EmailMessage:
        msg = EmailMessage()
        msg["From"] = self.addr_from.full
        msg["To"] = ", ".join([a.full for a in self.addr_to])
        msg["Subject"] = self.subject
        msg["Date"] = (self.sent_at or datetime.datetime.now()).strftime("%a, %d %b %Y %H:%M:%S %z")
        msg["In-Reply-To"] = self.in_reply_to
        msg.set_content(self.body)
        return msg


MailQueue = AnyQueue[SimpleEmail]
