from enum import Enum

from loguru import logger

from llmailbot.email.model import IMAPMessage

try:
    import dkim
    import DNS
    from dkim import DKIMException
except ImportError as e:
    raise ImportError(
        "pydns and dkimpy are required for DKIM verification;"
        " install them with 'poetry install --extras dkim' or pip install llmailbot[dkim]"
    ) from e


class DnsError(Exception):
    pass


# The implementation in dkimpy doesn't follow CNAME records
# So it fails when the TXT record for DKIM is behind a CNAME
def get_dns_txt_recursive(name: str | bytes, timeout=5) -> bytes:
    """
    Return a TXT record associated with a DNS name.
    Follows CNAME records.
    """
    if isinstance(name, bytes):
        name = name.decode("utf-8")

    name = name.rstrip(".")
    response = DNS.DnsRequest(name, qtype="txt", timeout=timeout).req()

    if response is None:
        raise DnsError(f"DNS lookup for {name} returned no response")

    if not response.answers:
        raise DnsError(f"DNS lookup for {name} returned no answers")

    record_cname: str | None = None
    record_txt: bytes | None = None
    for answer in response.answers:
        rectype = answer["typename"].lower()
        if rectype == "txt":
            record_txt = b"".join(answer["data"])
        elif rectype == "cname":
            record_cname = answer["data"][0]

    if record_txt is not None:
        return record_txt

    if record_cname is not None:
        return get_dns_txt_recursive(record_cname, timeout)

    raise DnsError(f"DNS lookup for {name} returned no TXT or CNAME record")


class VerificationResult(Enum):
    PASS = 0
    FAIL = 1
    MISSING = 2


def verify_dkim_signatures(email: IMAPMessage, timeout: int = 5) -> VerificationResult:
    sigs = email.obj.get_all("DKIM-Signature")
    if not sigs:
        return VerificationResult.MISSING
    sig_indices = list(range(len(sigs)))

    verifier = dkim.DKIM(email._raw_message_data, logger=logger, timeout=timeout)
    for idx in sig_indices:
        if not verifier.verify(idx, dnsfunc=get_dns_txt_recursive):
            return VerificationResult.FAIL
    return VerificationResult.PASS


__all__ = ["verify_dkim_signatures", "DnsError", "VerificationResult", "DKIMException"]
