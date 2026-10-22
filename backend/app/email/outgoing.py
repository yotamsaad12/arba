"""Outgoing email for notifications. SMTP (Mailpit in dev, a provider in production) or console."""

import asyncio
import html
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

log = logging.getLogger(__name__)


_PAGE = "margin:0;background:#f3efe6"
_WRAP = "max-width:560px;margin:0 auto;padding:24px;font-family:Arial,sans-serif;color:#172033"
_LOGO = "font-size:22px;font-weight:800;color:#1e3a5f;direction:ltr;text-align:right"
_CARD = (
    "background:#fff;border:2px solid #172033;border-radius:16px;padding:20px;"
    "margin-top:12px;box-shadow:5px 5px 0 #172033"
)
_BUTTON = (
    "background:#172033;color:#fff;padding:12px 22px;border-radius:999px;"
    "text-decoration:none;font-weight:bold"
)
_FOOTER = "font-size:12px;color:#5d6475"


def build(
    to: str, subject: str, text: str, link: str | None, button: str = "פתיחה ב-Arba"
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(f"{text}\n\n{link}" if link else text)

    paragraphs = "".join(
        f"<p style='margin:0 0 12px'>{html.escape(p)}</p>" for p in text.split("\n") if p
    )
    action = (
        f"<p style='margin:24px 0'><a href='{html.escape(link)}' style='{_BUTTON}'>"
        f"{html.escape(button)}</a></p>"
        if link
        else ""
    )
    message.add_alternative(
        f'<!doctype html><html lang="he" dir="rtl"><body style="{_PAGE}">'
        f'<div style="{_WRAP}"><div style="{_LOGO}">Arba</div>'
        f'<div style="{_CARD}"><h2 style="margin:0 0 12px">{html.escape(subject)}</h2>'
        f"{paragraphs}{action}</div>"
        f'<p style="{_FOOTER}">אפשר לשנות את ההתראות בהגדרות החשבון.</p></div></body></html>',
        subtype="html",
    )
    return message


async def send(message: EmailMessage) -> bool:
    """Sends the message. False if it was held back by the dev recipient allow-list."""
    allowed = settings.email_allowed_recipients
    if allowed is not None and message["To"].lower() not in {a.lower() for a in allowed}:
        log.info("email to %s not sent: not in ARBA_EMAIL_ALLOWED_RECIPIENTS", message["To"])
        return False
    if settings.email_backend == "console":
        log.info("email to %s: %s", message["To"], message["Subject"])
        return True
    await asyncio.to_thread(_smtp_send, message)
    return True


def _smtp_send(message: EmailMessage) -> None:
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_user and settings.smtp_password:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)
