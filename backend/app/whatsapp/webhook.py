"""Meta's WhatsApp webhook: signature check and parsing into simple events.

https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/payload-examples
"""

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.whatsapp.phone import normalize_phone


def sign(body: bytes) -> str:
    digest = hmac.new(settings.whatsapp_app_secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def valid_signature(body: bytes, header: str | None) -> bool:
    return bool(header) and hmac.compare_digest(sign(body), header or "")


@dataclass
class Incoming:
    phone: str
    message_id: str
    # The payload of a pressed button, or None for typed text.
    button: str | None
    text: str


@dataclass
class StatusUpdate:
    message_id: str
    status: str  # sent | delivered | read | failed
    error: str | None


def parse(payload: dict[str, Any]) -> list[Incoming | StatusUpdate]:
    events: list[Incoming | StatusUpdate] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for m in value.get("messages") or []:
                phone = normalize_phone("+" + str(m.get("from", "")))
                if not phone:
                    continue
                kind = m.get("type")
                if kind == "button":  # quick reply on a template
                    button = m.get("button") or {}
                    events.append(
                        Incoming(
                            phone, m.get("id", ""), button.get("payload"), button.get("text", "")
                        )
                    )
                elif kind == "interactive":  # reply button on a free-form message
                    reply = (m.get("interactive") or {}).get("button_reply") or {}
                    events.append(
                        Incoming(phone, m.get("id", ""), reply.get("id"), reply.get("title", ""))
                    )
                elif kind == "text":
                    events.append(
                        Incoming(
                            phone, m.get("id", ""), None, (m.get("text") or {}).get("body", "")
                        )
                    )
            for s in value.get("statuses") or []:
                errors = s.get("errors") or []
                error = errors[0].get("title") if errors else None
                events.append(StatusUpdate(s.get("id", ""), s.get("status", ""), error))
    return events


def message_payload(phone: str, message_id: str, *, button: str | None = None,
                    title: str = "", text: str = "") -> dict[str, Any]:  # fmt: skip
    """A webhook body in Meta's shape, as the simulator (and tests) send it."""
    if button:
        message: dict[str, Any] = {
            "type": "interactive",
            "interactive": {"type": "button_reply", "button_reply": {"id": button, "title": title}},
        }
    else:
        message = {"type": "text", "text": {"body": text}}
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [{"from": phone.lstrip("+"), "id": message_id, **message}],
                        },
                    }
                ]
            }
        ],
    }
