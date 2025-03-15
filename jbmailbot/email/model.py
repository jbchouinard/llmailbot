from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path

from imap_tools.message import MailMessage


@dataclass
class SimpleEmail:
    addr_from: str
    addr_to: tuple[str, ...]
    subject: str
    body: str
    sent_at: datetime.datetime | None = None
    message_uid: str | None = None
    message_id: str | None = None
    in_reply_to: str | None = None
    references: str | None = None
    attachments: dict[str, Path] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"From: {self.addr_from}\nTo: {self.addr_to}\nSubject: {self.subject}\n{self.body}"

    def summary(self) -> str:
        return (
            f"Email From: {self.addr_from} To: {self.addr_to} Date: {self.sent_at} "
            f"UID: {self.message_uid} ID: {self.message_id}"
        )

    def attach(self, filename: str, path: Path) -> None:
        self.attachments[filename] = path

    @classmethod
    def from_message(cls, message: MailMessage) -> "SimpleEmail":
        return cls(
            addr_from=message.from_,
            addr_to=message.to,
            subject=message.subject,
            body=message.text,
            sent_at=message.date,
            message_uid=message.uid,
            message_id=message.obj.get("Message-Id"),
            in_reply_to=message.obj.get("In-Reply-To"),
            references=message.obj.get("References"),
            # TODO: download attachments?
            attachments={},
        )

    @classmethod
    def reply(cls, email: SimpleEmail, addr_from: str, body: str) -> SimpleEmail:
        return cls(
            addr_from=addr_from,
            addr_to=(email.addr_from,),
            subject=email.subject,
            body=body,
            in_reply_to=email.message_id,
            references=email.references,
        )
