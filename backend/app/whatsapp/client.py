"""Sending WhatsApp messages: Meta's Cloud API in production, a database-backed simulator in dev."""

import uuid
from typing import Protocol

import httpx

from app.core.config import settings
from app.db.models import SimulatedWhatsApp
from app.db.session import SessionLocal
from app.whatsapp.templates import Template, clean_param

Button = tuple[str, str]  # (payload id, title)


class WhatsAppError(Exception):
    pass


class WhatsAppSender(Protocol):
    async def send_template(
        self, to: str, template: Template, params: list[str], payloads: list[str] | None = None
    ) -> str: ...

    async def send_buttons(self, to: str, text: str, buttons: list[Button]) -> str: ...

    async def send_text(self, to: str, text: str) -> str: ...


class CloudSender:
    """https://developers.facebook.com/docs/whatsapp/cloud-api/messages"""

    def __init__(self) -> None:
        self.url = (
            f"https://graph.facebook.com/{settings.whatsapp_api_version}/"
            f"{settings.whatsapp_phone_number_id}/messages"
        )
        self.headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}

    async def _post(self, to: str, message: dict[str, object]) -> str:
        body = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to.lstrip("+"),
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(self.url, headers=self.headers, json=body | message)
        if response.status_code >= 400:
            raise WhatsAppError(f"{response.status_code}: {response.text[:500]}")
        return str(response.json()["messages"][0]["id"])

    async def send_template(
        self, to: str, template: Template, params: list[str], payloads: list[str] | None = None
    ) -> str:
        values = [clean_param(p) for p in params]
        components: list[dict[str, object]] = [
            {"type": "body", "parameters": [{"type": "text", "text": v} for v in values]}
        ]
        if template.copy_code:
            components.append(
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [{"type": "text", "text": values[0]}],
                }
            )
        for i, payload in enumerate(payloads or []):
            components.append(
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": str(i),
                    "parameters": [{"type": "payload", "payload": payload}],
                }
            )
        return await self._post(
            to,
            {
                "type": "template",
                "template": {
                    "name": template.name,
                    "language": {"code": settings.whatsapp_language},
                    "components": components,
                },
            },
        )

    async def send_buttons(self, to: str, text: str, buttons: list[Button]) -> str:
        # Free-form interactive message; only allowed within 24h of the person's last message.
        return await self._post(
            to,
            {
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": text[:1024]},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": bid, "title": title[:20]}}
                            for bid, title in buttons[:3]
                        ]
                    },
                },
            },
        )

    async def send_text(self, to: str, text: str) -> str:
        return await self._post(to, {"type": "text", "text": {"body": text, "preview_url": True}})


class SimulatorSender:
    """Keeps messages in the database; the /dev/whatsapp page shows them as a chat."""

    async def _store(self, to: str, text: str, buttons: list[Button]) -> str:
        message_id = f"sim.{uuid.uuid4().hex}"
        async with SessionLocal() as db:
            db.add(
                SimulatedWhatsApp(
                    phone=to,
                    direction="out",
                    text=text,
                    buttons=[{"id": bid, "title": title} for bid, title in buttons],
                    provider_message_id=message_id,
                )
            )
            await db.commit()
        return message_id

    async def send_template(
        self, to: str, template: Template, params: list[str], payloads: list[str] | None = None
    ) -> str:
        text = template.render([clean_param(p) for p in params])
        return await self._store(
            to, text, list(zip(payloads or [], template.buttons, strict=False))
        )

    async def send_buttons(self, to: str, text: str, buttons: list[Button]) -> str:
        return await self._store(to, text, buttons)

    async def send_text(self, to: str, text: str) -> str:
        return await self._store(to, text, [])


def get_whatsapp() -> WhatsAppSender | None:
    if settings.whatsapp_provider == "cloud":
        return CloudSender()
    if settings.whatsapp_provider == "simulator":
        return SimulatorSender()
    return None
