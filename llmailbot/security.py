import abc
import datetime
from enum import Enum
from typing import Iterable, NamedTuple

from loguru import logger
from pydantic import SecretStr

from llmailbot.config import FilterMode, SecurityConfig
from llmailbot.email.model import SimpleEmail


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
    def check(self, email: SimpleEmail) -> RuleResult:
        pass


class AllowAll(Rule):
    def check(self, email: SimpleEmail) -> RuleResult:
        return RuleResult(Action.ALLOW, None)


class SecretKeyRule(Rule):
    """
    Checks if the email body starts with a secret key.
    If it does, the secret key is removed from the body.
    """

    def __init__(self, secret_key: SecretStr):
        self.secret_key = secret_key

    def check(self, email: SimpleEmail) -> RuleResult:
        key = self.secret_key.get_secret_value()
        body = email.body.lstrip()
        if body.startswith(key):
            email.body = email.body[len(key) :].lstrip()
            return RuleResult(Action.ALLOW, None)
        return RuleResult(Action.BLOCK, "secret key check failed")


class FilterSenderRule(Rule):
    """
    Checks if the email sender is in a list of allowed or denied addresses.
    """

    def __init__(self, mode: FilterMode, addresses: Iterable[str]):
        self.mode = mode
        self.addresses = set()
        self.domains = set()
        for addr in addresses:
            name, domain = addr.split("@", 1)
            if name == "*":
                self.domains.add(domain)
            else:
                self.addresses.add(addr)

    def is_in_list(self, addr: str) -> bool:
        _, domain = addr.split("@", 1)
        return domain in self.domains or addr in self.addresses

    def check(self, email: SimpleEmail) -> RuleResult:
        sender = email.addr_from.email
        sender_in_list = self.is_in_list(sender)
        if self.mode == FilterMode.DENYLIST and sender_in_list:
            return RuleResult(Action.BLOCK, f"{sender} is in deny list")
        if self.mode == FilterMode.ALLOWLIST and not sender_in_list:
            return RuleResult(Action.BLOCK, f"{sender} is not in allow list")
        return RuleResult(Action.ALLOW, None)


class RateLimitRule(Rule):
    """
    Global rate limit check.
    """

    def __init__(self, duration: datetime.timedelta, limit: int, name: str = ""):
        self.duration = duration
        logger.trace("Rate limit duration: {}", self.duration)
        self.limit = limit
        self.count = 0
        self.limit_expiry = datetime.datetime.now() + self.duration
        self.name = name

    def _reset(self, now: datetime.datetime) -> None:
        self.count = 0
        self.limit_expiry = now + self.duration
        logger.trace(
            "rate limit reset {} {}/{} {}",
            self.name,
            self.count,
            self.limit,
            self.limit_expiry,
        )

    def _is_expired(self, now: datetime.datetime | None = None) -> bool:
        now = now or datetime.datetime.now()
        return now > self.limit_expiry

    def _increase_and_check(self) -> RuleResult:
        now = datetime.datetime.now()
        if self._is_expired(now):
            self._reset(now)

        self.count += 1
        logger.trace(
            "rate limit {} {}/{} until {}", self.name, self.count, self.limit, self.limit_expiry
        )
        if self.count > self.limit:
            return RuleResult(
                Action.BLOCK,
                f"rate limit exceeded - {self.name} - "
                f"{self.count}/{self.limit} until {self.limit_expiry}",
            )
        return RuleResult(Action.ALLOW, None)

    def check(self, email: SimpleEmail) -> RuleResult:
        return self._increase_and_check()


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

        return self.rate_limits[key]._increase_and_check()

    def check(self, email: SimpleEmail) -> RuleResult:
        return self._increase_and_check(email.addr_from.email)


class RateLimitPerDomainRule(RateLimitPerSenderRule):
    def check(self, email: SimpleEmail) -> RuleResult:
        _, domain = email.addr_from.email.split("@", 1)
        return self._increase_and_check(domain)


class SecurityFilter:
    """
    SecurityFilter filters emails based on a list of rules.
    """

    def __init__(self, rules: Iterable[Rule]):
        self.rules = list(rules)

    def apply(self, email: SimpleEmail) -> SimpleEmail | None:
        for check in self.rules:
            result, reason = check.check(email)
            if result == Action.BLOCK:
                logger.log("SECURITY", "BLOCKED - {} - {}", reason, email.summary())
                return None
        return email


def make_security_filter(config: SecurityConfig, name_prefix: str = "") -> SecurityFilter | None:
    rules = []
    if config.secret_key:
        rules.append(SecretKeyRule(config.secret_key))
    if config.filter_from:
        rules.append(FilterSenderRule(config.filter_from.mode, config.filter_from.addresses))
    if config.rate_limit_global and config.rate_limit_global.limit is not None:
        rules.append(
            RateLimitRule(
                config.rate_limit_global._window_timedelta,
                config.rate_limit_global.limit,
                f"{name_prefix}global",
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
    if config.rate_limit_per_sender and config.rate_limit_per_sender.limit is not None:
        rules.append(
            RateLimitPerSenderRule(
                config.rate_limit_per_sender._window_timedelta,
                config.rate_limit_per_sender.limit,
                f"{name_prefix}per-sender",
            )
        )
    if not rules:
        return None
    return SecurityFilter(rules)
