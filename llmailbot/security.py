import abc
import datetime
import re
from enum import Enum
from typing import Iterable, NamedTuple

from loguru import logger

from llmailbot.config import FilterMode, SecurityConfig
from llmailbot.email.model import IMAPMessage
from llmailbot.enums import VerifyMode
from llmailbot.ratelimit import LimitResult, RateLimiter


class Action(Enum):
    BLOCK = 0
    ALLOW = 1


class RuleResult(NamedTuple):
    action: Action
    reason: str | None

    @property
    def is_blocked(self) -> bool:
        return self.action == Action.BLOCK


class Rule(abc.ABC):
    @abc.abstractmethod
    def check(self, email: IMAPMessage) -> RuleResult:
        pass


VerifyDKIM: type[Rule] = None  # pyright: ignore[reportAssignmentType]

try:
    from llmailbot.dkim import DKIMException, DnsError, VerificationResult, verify_dkim_signatures

    class VerifyDKIM(Rule):
        """
        Blocks emails with an invalid DKIM signature.

        In strict mode, blocks emails without a DKIM signature.

        DKIM verification is most likely already done by the mail server,
        but not necessarily strictly.

        This check helps prevent address spoofing, but will block
        some legitimate emails.
        """

        def __init__(self, strict: bool):
            self.strict = strict

        def check(self, email: IMAPMessage) -> RuleResult:
            dkim_signatures = email.obj.get_all("DKIM-Signature")
            if not dkim_signatures:
                if self.strict:
                    return RuleResult(Action.BLOCK, "No DKIM signature")
                else:
                    return RuleResult(Action.ALLOW, None)

            try:
                result = verify_dkim_signatures(email)
            except DnsError as exc:
                logger.exception("DNS error while verifying DKIM signature")
                return RuleResult(Action.BLOCK, f"DKIM DNS error ({str(exc)})")
            except DKIMException as exc:
                logger.exception("DKIM verification error")
                return RuleResult(Action.BLOCK, f"DKIM verification error ({str(exc)})")

            if result == VerificationResult.FAIL:
                return RuleResult(Action.BLOCK, "DKIM verification failed")
            if result == VerificationResult.PASS:
                return RuleResult(Action.ALLOW, None)
            if self.strict:
                return RuleResult(Action.BLOCK, "No DKIM signature")
            else:
                return RuleResult(Action.ALLOW, None)

except ImportError:
    logger.debug("dkim extras are not installed; VerifyDKIM is not available")


RE_SMTP_MAILFROM = re.compile(r"smtp.mailfrom=(?P<mailfrom>[^;\s]+)", re.MULTILINE)


class VerifyMailFrom(Rule):
    """
    Verifies that SMTP MAIL FROM matches the From header, by
    looking for smtp.mailfrom in Authentication-Results headers.

    In strict mode, blocks emails for which smtp.mailfrom cannot be
    determined.

    This check helps prevent address spoofing, but will block
    many legitimate emails.
    """

    AUTHENTICATION_RESULTS_HEADERS = (
        "Authentication-Results",
        "ARC-Authentication-Results",
    )

    def __init__(self, strict: bool = True):
        self.strict = strict

    def check(self, email: IMAPMessage) -> RuleResult:
        smtp_mailfrom = None
        found_in_header = None
        for header in self.AUTHENTICATION_RESULTS_HEADERS:
            if m := RE_SMTP_MAILFROM.search(email.obj.get(header, "")):
                smtp_mailfrom = m.group("mailfrom")
                found_in_header = header
                break

        if smtp_mailfrom is None:
            if self.strict:
                return RuleResult(Action.BLOCK, "smtp.mailfrom not found")
            else:
                return RuleResult(Action.ALLOW, None)

        from_email = email.addr_from.email
        if smtp_mailfrom == from_email:
            return RuleResult(Action.ALLOW, None)
        else:
            return RuleResult(
                Action.BLOCK,
                f"smtp.mailfrom={smtp_mailfrom} in {found_in_header} "
                f"header does not match From={from_email}",
            )


class VerifyXMailFrom(Rule):
    """
    Verifies that the X-Mail-From header matches the From header.

    X-Mail-From is a custom header used by at least one provider
    (Fastmail) to set to the value of SMTP MAIL FROM.

    In strict mode, blocks emails which don't have the X-Mail-From header.

    This check helps prevent address spoofing, but will block
    many legitimate emails.
    """

    MAIL_FROM_HEADER = "X-Mail-From"

    def __init__(self, strict: bool = True):
        self.strict = strict

    def check(self, email: IMAPMessage) -> RuleResult:
        x_mail_from = email.obj.get(self.MAIL_FROM_HEADER)
        if self.strict and x_mail_from is None:
            return RuleResult(Action.BLOCK, f"{self.MAIL_FROM_HEADER} header is missing")
        if x_mail_from != email.addr_from.email:
            return RuleResult(
                Action.BLOCK, f"{self.MAIL_FROM_HEADER} header does not match From header"
            )
        return RuleResult(Action.ALLOW, None)


class FilterHeader(Rule):
    """
    Filter based on the value of an arbitrary email header.

    In strict mode, blocks emails which don't have the header.
    """

    def __init__(
        self,
        header: str,
        values: Iterable[str],
        mode: FilterMode,
        strict: bool = True,
    ):
        self.header = header
        self.values = set(values)
        self.mode = mode
        self.strict = strict

    def check(self, email: IMAPMessage) -> RuleResult:
        header_value = email.obj.get(self.header)
        if header_value is None:
            if self.strict:
                return RuleResult(Action.BLOCK, f"{self.header} header is missing")
            else:
                return RuleResult(Action.ALLOW, None)

        if self.mode == FilterMode.DENYLIST and header_value in self.values:
            return RuleResult(Action.BLOCK, f"{self.header} header value is in deny list")
        if self.mode == FilterMode.ALLOWLIST and header_value not in self.values:
            return RuleResult(Action.BLOCK, f"{self.header} header value is not in allow list")
        return RuleResult(Action.ALLOW, None)


class FilterFrom(Rule):
    """
    Checks if the email sender is in a list of allowed or denied addresses.
    """

    def __init__(
        self,
        mode: FilterMode,
        addresses: Iterable[str],
    ):
        self.mode = mode
        self.addresses = set()
        self.domains = set()
        for addr in addresses:
            name, domain = addr.split("@", 1)
            if name == "*":
                self.domains.add(domain)
            else:
                self.addresses.add(addr)

        logger.debug("FilterFrom: {} {} {}", mode, self.addresses, self.domains)

    def is_in_list(self, addr: str) -> bool:
        _, domain = addr.split("@", 1)
        in_list = domain in self.domains or addr in self.addresses
        return in_list

    def check(self, email: IMAPMessage) -> RuleResult:
        sender = email.addr_from.email
        if sender is None:
            return RuleResult(Action.BLOCK, "From header is missing")

        sender_in_list = self.is_in_list(sender)
        if self.mode == FilterMode.DENYLIST and sender_in_list:
            return RuleResult(Action.BLOCK, f"{sender} is in deny list")
        if self.mode == FilterMode.ALLOWLIST and not sender_in_list:
            return RuleResult(Action.BLOCK, f"{sender} is not in allow list")
        return RuleResult(Action.ALLOW, None)


class RateLimitRule(RateLimiter, Rule):
    """
    Global rate limit check.
    """

    def __init__(self, duration: datetime.timedelta, limit: int, name: str = ""):
        self.name = name
        super().__init__(duration, limit)

    def _reset(self, now: datetime.datetime) -> None:
        super()._reset(now)
        logger.trace(
            "rate limit reset {} {}/{} {}",
            self.name,
            self._limit_count,
            self.limit,
            self._limit_expiry,
        )

    def count(self) -> LimitResult:
        res = super().count()
        logger.trace(
            "rate limit {} {}/{} until {}",
            self.name,
            self._limit_count,
            self.limit,
            self._limit_expiry,
        )
        return res

    def _check(self) -> RuleResult:
        limit_result = self.count()
        if limit_result == LimitResult.EXCEEDED:
            return RuleResult(Action.BLOCK, f"rate limit {self.name} exceeded")
        return RuleResult(Action.ALLOW, None)

    def check(self, email: IMAPMessage) -> RuleResult:
        return self._check()


class RateLimitPerSenderRule(Rule):
    """
    Per-sender rate limit check.
    """

    def __init__(self, duration: datetime.timedelta, limit: int, name: str = ""):
        self.rate_limits: dict[str, RateLimitRule] = {}
        self.duration = duration
        self.limit = limit
        self._next_purge = datetime.datetime.now() + self.duration
        self.name = name

    def _purge(self, now: datetime.datetime) -> None:
        for key, rate_limit in self.rate_limits.items():
            if rate_limit._is_expired(now):
                del self.rate_limits[key]

    def _increase_and_check(self, key: str) -> RuleResult:
        now = datetime.datetime.now()

        if key in self.rate_limits:
            if self.rate_limits[key]._is_expired(now):
                self.rate_limits[key]._reset(now)
        else:
            self.rate_limits[key] = RateLimitRule(self.duration, self.limit, f"{self.name}/{key}")

        if now > self._next_purge:
            self._purge(now)
            self._next_purge = now + self.duration

        return self.rate_limits[key]._check()

    def check(self, email: IMAPMessage) -> RuleResult:
        return self._increase_and_check(email.addr_from.email)


class RateLimitPerDomainRule(RateLimitPerSenderRule):
    def check(self, email: IMAPMessage) -> RuleResult:
        _, domain = email.addr_from.email.split("@", 1)
        return self._increase_and_check(domain)


class SecurityFilter:
    """
    SecurityFilter applies the provided rules to an email to
    decide whether to block or allow it.
    """

    def __init__(self, rules: Iterable[Rule]):
        self.rules = list(rules)

    def apply(self, email: IMAPMessage) -> Action:
        for check in self.rules:
            result, reason = check.check(email)
            if result == Action.BLOCK:
                logger.log("SECURITY", "BLOCKED - {} - {}", reason, email.summary())
                return Action.BLOCK
        return Action.ALLOW


def make_security_filter(config: SecurityConfig, name_prefix: str = "") -> SecurityFilter | None:
    rules = []

    if not config.allow_from and config.allow_from_all_i_want_to_spend_it_all:
        pass
    else:
        rules.append(FilterFrom(FilterMode.ALLOWLIST, config.allow_from))

    if config.block_from:
        rules.append(FilterFrom(FilterMode.DENYLIST, config.block_from))

    if config.verify_mail_from == VerifyMode.IF_PRESENT:
        rules.append(VerifyMailFrom(strict=False))
    elif config.verify_mail_from == VerifyMode.ALWAYS:
        rules.append(VerifyMailFrom(strict=True))

    if config.verify_x_mail_from == VerifyMode.IF_PRESENT:
        rules.append(VerifyXMailFrom(strict=False))
    elif config.verify_x_mail_from == VerifyMode.ALWAYS:
        rules.append(VerifyXMailFrom(strict=True))

    if config.verify_dkim == VerifyMode.IF_PRESENT:
        assert VerifyDKIM is not None, (
            "dkim extras not installed, VerifyDKIM option is not available"
        )
        rules.append(VerifyDKIM(strict=False))
    elif config.verify_dkim == VerifyMode.ALWAYS:
        assert VerifyDKIM is not None, (
            "dkim extras not installed, VerifyDKIM option is not available"
        )
        rules.append(VerifyDKIM(strict=True))

    for fheader in config.filter_headers or []:
        if fheader.verify == VerifyMode.IF_PRESENT:
            rules.append(FilterHeader(fheader.header, fheader.values, fheader.mode, False))
        elif fheader.verify == VerifyMode.ALWAYS:
            rules.append(FilterHeader(fheader.header, fheader.values, fheader.mode, True))

    if config.rate_limit_per_sender and config.rate_limit_per_sender.limit is not None:
        rules.append(
            RateLimitPerSenderRule(
                config.rate_limit_per_sender._window_timedelta,
                config.rate_limit_per_sender.limit,
                f"{name_prefix}per-sender",
            )
        )

    if config.rate_limit_per_domain and config.rate_limit_per_domain.limit is not None:
        rules.append(
            RateLimitPerDomainRule(
                config.rate_limit_per_domain._window_timedelta,
                config.rate_limit_per_domain.limit,
                f"{name_prefix}per-domain",
            )
        )

    if config.rate_limit and config.rate_limit.limit is not None:
        rules.append(
            RateLimitRule(
                config.rate_limit._window_timedelta,
                config.rate_limit.limit,
                f"{name_prefix}global",
            )
        )

    if not rules:
        return None
    return SecurityFilter(rules)
