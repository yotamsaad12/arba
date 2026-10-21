"""Provider-neutral inbound email, and the parser for Postmark's inbound webhook JSON.

Postmark format: https://postmarkapp.com/developer/webhooks/inbound-webhook
"""

import base64
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any


@dataclass
class ParsedAttachment:
    name: str
    content_type: str
    data: bytes
    content_id: str | None = None


@dataclass
class ParsedEmail:
    provider_id: str
    message_id: str
    in_reply_to: str | None
    references: list[str]
    from_email: str
    from_name: str | None
    to: list[str]
    cc: list[str]
    # Every address the mail was delivered for, used to find the project.
    recipients: list[str]
    subject: str
    text: str
    sent_at: datetime
    attachments: list[ParsedAttachment] = field(default_factory=list)


_ID = re.compile(r"<([^<>\s]+)>")


def normalize_message_id(value: str | None) -> str | None:
    if not value:
        return None
    match = _ID.search(value)
    return (match.group(1) if match else value.strip()).lower() or None


def message_ids(value: str | None) -> list[str]:
    """All ids in a References header, oldest first."""
    if not value:
        return []
    found = _ID.findall(value)
    return [i.lower() for i in found] if found else [v.lower() for v in value.split() if v]


# Reply/forward prefixes in English and Hebrew mail clients (Outlook, Gmail, Apple Mail).
_PREFIX = re.compile(
    r"^\s*((re|fw|fwd|aw|wg|השב|תשובה|הועבר|העבר|מועבר)\s*(\[\d+\])?\s*[:：]\s*)+", re.I
)


def strip_reply_prefixes(subject: str) -> str:
    return re.sub(r"\s+", " ", _PREFIX.sub("", subject or "")).strip()


def normalize_subject(subject: str) -> str:
    return strip_reply_prefixes(subject).lower()


class _TextExtractor(HTMLParser):
    _BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "table", "blockquote"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in ("script", "style", "head"):
            self._skip += 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "head"):
            self._skip = max(0, self._skip - 1)
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(html)
    text = "".join(extractor.parts)
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _header(headers: list[dict[str, str]], name: str) -> str | None:
    for h in headers:
        if h.get("Name", "").lower() == name.lower():
            return h.get("Value")
    return None


def _addresses(full: list[dict[str, Any]] | None, raw: str | None) -> list[str]:
    if full:
        return [a["Email"].lower() for a in full if a.get("Email")]
    return [addr.lower() for _, addr in getaddresses([raw or ""]) if addr]


def parse_postmark(payload: dict[str, Any]) -> ParsedEmail:
    headers = payload.get("Headers") or []
    provider_id = str(payload.get("MessageID") or "")
    from_full = payload.get("FromFull") or {}
    to = _addresses(payload.get("ToFull"), payload.get("To"))
    cc = _addresses(payload.get("CcFull"), payload.get("Cc"))
    original = (payload.get("OriginalRecipient") or "").lower()

    sent_at = datetime.now(UTC)
    if payload.get("Date"):
        try:
            sent_at = parsedate_to_datetime(payload["Date"])
            if sent_at.tzinfo is None:
                sent_at = sent_at.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            pass

    text = (payload.get("TextBody") or "").strip()
    if not text and payload.get("HtmlBody"):
        text = html_to_text(payload["HtmlBody"])

    attachments = [
        ParsedAttachment(
            name=a.get("Name") or "attachment",
            content_type=a.get("ContentType") or "application/octet-stream",
            data=base64.b64decode(a.get("Content") or ""),
            content_id=a.get("ContentID") or None,
        )
        for a in payload.get("Attachments") or []
    ]

    # Postmark's MessageID is its own id; the RFC Message-ID is in the headers. Some
    # senders omit it, so fall back to the provider id to keep messages unique.
    message_id = normalize_message_id(_header(headers, "Message-ID")) or f"postmark-{provider_id}"

    return ParsedEmail(
        provider_id=provider_id,
        message_id=message_id,
        in_reply_to=normalize_message_id(_header(headers, "In-Reply-To")),
        references=message_ids(_header(headers, "References")),
        from_email=(from_full.get("Email") or payload.get("From") or "").lower(),
        from_name=from_full.get("Name") or payload.get("FromName") or None,
        to=to,
        cc=cc,
        recipients=list(dict.fromkeys([*to, *cc, *([original] if original else [])])),
        subject=(payload.get("Subject") or "").strip(),
        text=text,
        sent_at=sent_at,
        attachments=attachments,
    )
