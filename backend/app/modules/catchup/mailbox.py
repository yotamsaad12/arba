"""Reading a person's mailbox, once, with their permission.

Gmail: OAuth with the read-only scope and online access (no refresh token). The access token
lives only in memory while the scan runs, and Arba revokes it when the scan ends.
"""

import base64
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime
from typing import Protocol
from urllib.parse import urlencode

import httpx
import jwt

from app.core.config import settings
from app.core.enums import MailboxProvider
from app.core.errors import AppError
from app.db.models import Project
from app.email.parsing import ParsedEmail, parse_rfc822
from app.modules.catchup.search import MailSearch

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE = "https://oauth2.googleapis.com/revoke"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
GMAIL_SCOPES = "openid email https://www.googleapis.com/auth/gmail.readonly"
STATE_MINUTES = 15


class Mailbox(Protocol):
    account_email: str

    def search(self, search: MailSearch, limit: int) -> AsyncIterator[ParsedEmail]: ...

    async def close(self) -> None: ...


def configured_provider() -> MailboxProvider | None:
    choice = settings.mailbox_provider
    if choice == "auto":
        if settings.google_client_id and settings.google_client_secret:
            return MailboxProvider.gmail
        return MailboxProvider.simulator if settings.env in ("dev", "test") else None
    return None if choice == "disabled" else MailboxProvider(choice)


# --- Gmail ----------------------------------------------------------------------------


def redirect_uri() -> str:
    return f"{settings.app_url}/api/v1/mailbox/google/callback"


def google_auth_url(project_id: uuid.UUID, user_id: uuid.UUID, login_hint: str) -> str:
    state = jwt.encode(
        {
            "purpose": "mailbox",
            "sub": str(user_id),
            "project": str(project_id),
            "exp": datetime.now(UTC) + timedelta(minutes=STATE_MINUTES),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    return f"{GOOGLE_AUTH}?" + urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": redirect_uri(),
            "response_type": "code",
            "scope": GMAIL_SCOPES,
            "access_type": "online",
            "include_granted_scopes": "true",
            "login_hint": login_hint,
            "state": state,
        }
    )


def read_state(state: str) -> tuple[uuid.UUID, uuid.UUID]:
    """(user id, project id) from the state Google sends back."""
    try:
        claims = jwt.decode(state, settings.jwt_secret, algorithms=["HS256"])
        if claims.get("purpose") != "mailbox":
            raise ValueError("wrong purpose")
        return uuid.UUID(claims["sub"]), uuid.UUID(claims["project"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise AppError(400, "invalid_state", "the mailbox link expired; try again") from exc


class GmailMailbox:
    def __init__(self, access_token: str, account_email: str) -> None:
        self.token = access_token
        self.account_email = account_email
        self.http = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {access_token}"}, timeout=30
        )

    @classmethod
    async def from_code(cls, code: str) -> "GmailMailbox":
        async with httpx.AsyncClient(timeout=30) as http:
            response = await http.post(
                GOOGLE_TOKEN,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": redirect_uri(),
                    "grant_type": "authorization_code",
                },
            )
            if response.status_code != 200:
                raise AppError(400, "mailbox_denied", "Google did not grant mailbox access")
            granted = response.json()
            if "gmail.readonly" not in granted.get("scope", ""):
                raise AppError(400, "mailbox_denied", "mailbox access was not granted")
            token = granted["access_token"]
            profile = await http.get(
                f"{GMAIL}/profile", headers={"Authorization": f"Bearer {token}"}
            )
            profile.raise_for_status()
        return cls(token, profile.json()["emailAddress"].lower())

    async def search(self, search: MailSearch, limit: int) -> AsyncIterator[ParsedEmail]:
        query, page, seen = search.gmail_query(), None, 0
        while seen < limit:
            params: dict[str, str | int] = {"q": query, "maxResults": min(100, limit - seen)}
            if page:
                params["pageToken"] = page
            listing = (await self.http.get(f"{GMAIL}/messages", params=params)).json()
            for ref in listing.get("messages", []):
                seen += 1
                raw = await self.http.get(f"{GMAIL}/messages/{ref['id']}", params={"format": "raw"})
                if raw.status_code == 200:
                    data = base64.urlsafe_b64decode(raw.json()["raw"])
                    yield parse_rfc822(data, f"gmail-{ref['id']}")
            page = listing.get("nextPageToken")
            if not page:
                break

    async def close(self) -> None:
        # Give the access back as soon as the scan is over.
        try:
            await self.http.post(GOOGLE_REVOKE, params={"token": self.token})
        finally:
            await self.http.aclose()


# --- Simulator ------------------------------------------------------------------------


@dataclass
class SimulatedMailbox:
    """A believable mailbox for a project under way: its permit, consultants' reports, a lab
    result, a request from the water corporation, and unrelated mail that must stay out."""

    project: Project
    account_email: str
    committee_domain: str = "muni.example.il"
    water_domain: str = "water.example.co.il"

    async def search(self, search: MailSearch, limit: int) -> AsyncIterator[ParsedEmail]:
        for i, raw in enumerate(self._mail()):
            if i >= limit:
                break
            email = parse_rfc822(raw, f"sim-{i}")
            # Stable ids, as in a real mailbox: scanning again finds the same messages.
            email.message_id = f"sim-{self.project.id}-{i}@sim.arba.local"
            if search.matches(email):
                yield email

    async def close(self) -> None:
        return None

    def _mail(self) -> list[bytes]:
        p = self.project
        place = p.address or p.municipality
        lot = f"גוש {p.gush} חלקה {p.helka}" if p.gush else place
        today = date.today()
        me = self.account_email
        return [
            _mail(
                f"רישוי בנייה <rishui@{self.committee_domain}>",
                me,
                f"היתר בנייה מס' {p.permit_number or '—'} - {place}",
                f"שלום,\nמצורף היתר הבנייה שאושר עבור {lot}.\nבברכה, מחלקת רישוי והנדסה",
                today - timedelta(days=420),
                ("היתר בנייה.pdf", "permit"),
            ),
            _mail(
                "משה המודד <moshe@modedim.example.co.il>",
                me,
                f"מפת סימון - {lot}",
                f"מצורפת מפת הסימון של המבנה במגרש, {lot}.",
                today - timedelta(days=300),
                ("מפת סימון.pdf", "survey"),
            ),
            _mail(
                "יועץ קרקע <office@karka.example.co.il>",
                me,
                f"דוח יועץ קרקע - {place}",
                f"מצורף דוח הקרקע והמלצות החפירה לפרויקט ב{place}.",
                today - timedelta(days=280),
                ("דוח קרקע.pdf", "soil"),
            ),
            _mail(
                "מעבדת בטון <lab@betonlab.example.co.il>",
                me,
                f"תוצאות בדיקת בטון - יסודות - {place}",
                f"תוצאות בדיקת הבטון ליציקת היסודות ב{place}: תקין.",
                today - timedelta(days=200),
                ("תוצאות בדיקת בטון.pdf", "concrete"),
            ),
            _mail(
                f"תאגיד המים <service@{self.water_domain}>",
                me,
                "בקשה להשלמת מסמכים - חיבור מים לבנייה",
                f"לצורך חיבור מים לבנייה ב{place} יש להשלים תוכנית אינסטלציה חתומה.",
                today - timedelta(days=60),
            ),
            _mail(
                me,
                "architect@studio.example.co.il",
                f"תיק תוכניות מאושר - {place}",
                f"מצרף את תיק התוכניות המאושר עם חותמת הוועדה. {lot}.",
                today - timedelta(days=400),
                ("תוכניות מאושרות.pdf", "plans"),
            ),
            # Not about the project: must not be imported.
            _mail(
                f"גבייה <arnona@{self.committee_domain}>",
                me,
                "חשבון ארנונה לתקופה הנוכחית",
                "מצורף חשבון הארנונה. ניתן לשלם באתר העירייה.",
                today - timedelta(days=30),
            ),
            _mail(
                "חנות כלי בית <deals@shop.example.com>",
                me,
                "מבצע סוף שבוע!",
                "הנחות על כל הכלים.",
                today - timedelta(days=10),
            ),
        ]


def _mail(
    sender: str,
    to: str,
    subject: str,
    text: str,
    day: date,
    attachment: tuple[str, str] | None = None,
) -> bytes:
    from app.scripts.send_test_email import sample_pdf

    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, to, subject
    msg["Date"] = format_datetime(datetime(day.year, day.month, day.day, 9, 30, tzinfo=UTC))
    msg.set_content(text)
    if attachment:
        name, title = attachment
        msg.add_attachment(sample_pdf(title), maintype="application", subtype="pdf", filename=name)
    return msg.as_bytes()
