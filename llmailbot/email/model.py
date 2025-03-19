from __future__ import annotations

import datetime
import email
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Self

from imap_tools.message import MailMessage
from imap_tools.utils import EmailAddress


@dataclass(slots=True)
class SimpleEmailMessage:
    """
    Used for composing simple plaintext messages.
    """

    addr_from: EmailAddress
    addrs_to: tuple[EmailAddress, ...]
    subject: str
    body: str
    date: datetime.datetime
    in_reply_to: str | None = None

    def __str__(self) -> str:
        from_str = self.addr_from.full
        to_str = ", ".join([a.full for a in self.addrs_to])
        return f"From: {from_str}\nTo: {to_str}\nSubject: {self.subject}\n{self.body}"

    def summary(self) -> str:
        ato = ", ".join([a.email for a in self.addrs_to])
        parts = ["Email", f"From: {self.addr_from.email}", f"To: {ato}"]
        if self.date:
            parts.append(f"Date: {self.date}")
        if self.in_reply_to:
            parts.append(f"In-Reply-To: {self.in_reply_to}")
        return " ".join(parts)

    def to_email_message(self) -> EmailMessage:
        msg = EmailMessage()
        msg["From"] = self.addr_from.full
        msg["To"] = ", ".join([a.full for a in self.addrs_to])
        msg["Subject"] = self.subject
        msg["Date"] = self.date.strftime("%a, %d %b %Y %H:%M:%S %z")
        msg["In-Reply-To"] = self.in_reply_to
        msg.set_content(self.body)
        return msg


@dataclass(slots=True)
class IMAPRawMessage:
    """
    Raw data from fetching emails with imap_tools.
    """

    message_data: bytes
    uid_data: bytes
    flag_data: list[bytes]

    @classmethod
    def from_fetch(cls, fetch_data: list) -> Self:
        message_data, uid_data, flag_data = MailMessage._get_message_data_parts(fetch_data)
        return cls(message_data=message_data, uid_data=uid_data, flag_data=flag_data)

    def parsed(self) -> IMAPMessage:
        return IMAPMessage(self)


class IMAPMessage(MailMessage):
    """
    Parsed email message from imap_tools.
    """

    def __init__(self, raw_email: IMAPRawMessage):
        self._raw_email = raw_email
        self.obj = email.message_from_bytes(raw_email.message_data)

    @property
    def _raw_message_data(self) -> bytes:
        return self._raw_email.message_data

    @property
    def _raw_flag_data(self) -> list[bytes]:
        return self._raw_email.flag_data

    @property
    def _raw_uid_data(self) -> bytes:
        return self._raw_email.uid_data

    @property
    def addr_from(self) -> EmailAddress:
        if not self.from_values:
            raise ValueError("message has no From address")
        return self.from_values

    @property
    def addrs_to(self) -> tuple[EmailAddress, ...]:
        return self.to_values

    @property
    def in_reply_to(self) -> str | None:
        return self.obj.get("In-Reply-To")

    @property
    def references(self) -> str | None:
        return self.obj.get("References")

    @property
    def message_id(self) -> str | None:
        return self.obj.get("Message-Id")

    def __str__(self) -> str:
        from_str = self.from_values.full if self.from_values else "unknown"
        to_str = ", ".join([a.full for a in self.addrs_to])
        return f"From: {from_str}\nTo: {to_str}\nSubject: {self.subject}\n{self.text}"

    def summary(self) -> str:
        ato = ", ".join([a.email for a in self.addrs_to])
        parts = ["Email", f"From: {self.addr_from.email}", f"To: {ato}"]
        if self.date:
            parts.append(f"Date: {self.date}")
        if self.message_id:
            parts.append(f"Message-Id: {self.message_id}")
        return " ".join(parts)

    def create_reply(self, addr_from: EmailAddress, body: str) -> SimpleEmailMessage:
        return SimpleEmailMessage(
            addr_from=addr_from,
            addrs_to=(self.addr_from,),
            subject=f"Re: {self.subject}",
            body=body,
            date=datetime.datetime.now(),
            in_reply_to=self.message_id,
        )
