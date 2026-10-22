"""WhatsApp message templates.

Messages Arba starts (outside the 24-hour window after a person wrote to us) must use templates
that Meta approved in advance. These definitions are the source of truth: the simulator renders
them, the Cloud sender references them by name, and `python -m app.scripts.whatsapp_templates`
prints (or submits) them for Meta's review.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

from app.core.config import settings


@dataclass(frozen=True)
class Template:
    name: str
    category: Literal["UTILITY", "AUTHENTICATION"]
    # Body with {{1}}, {{2}}… placeholders. Parameters can't contain line breaks.
    body: str
    examples: tuple[str, ...]
    # Quick-reply button titles (max 20 characters each); payloads are set per message.
    buttons: tuple[str, ...] = field(default=())
    # Authentication templates get Meta's "copy code" button instead.
    copy_code: bool = False

    def render(self, params: list[str]) -> str:
        return re.sub(r"\{\{(\d+)\}\}", lambda m: params[int(m.group(1)) - 1], self.body)

    def meta_definition(self) -> dict[str, object]:
        """The payload for POST /{waba-id}/message_templates."""
        if self.copy_code:
            components: list[dict[str, object]] = [
                {"type": "BODY", "add_security_recommendation": True},
                {"type": "FOOTER", "code_expiration_minutes": 10},
                {"type": "BUTTONS", "buttons": [{"type": "OTP", "otp_type": "COPY_CODE"}]},
            ]
        else:
            components = [
                {"type": "BODY", "text": self.body, "example": {"body_text": [list(self.examples)]}}
            ]
            if self.buttons:
                components.append(
                    {
                        "type": "BUTTONS",
                        "buttons": [{"type": "QUICK_REPLY", "text": b} for b in self.buttons],
                    }
                )
        return {
            "name": self.name,
            "category": self.category,
            "language": settings.whatsapp_language,
            "components": components,
        }


VERIFY_CODE = Template(
    name="arba_verify_code",
    category="AUTHENTICATION",
    # Meta writes the text of authentication templates itself; this is how it reads.
    body="{{1}} הוא קוד האימות שלך. מטעמי אבטחה, אל תשתפו את הקוד.",
    examples=("482913",),
    copy_code=True,
)

WELCOME = Template(
    name="arba_welcome",
    category="UTILITY",
    body=(
        "שלום {{1}}, WhatsApp מחובר עכשיו לחשבון Arba שלך ✅\n"
        "מעכשיו נעדכן אותך כאן במה שקורה בפרויקטים שלך, ונבקש ממך אישור רק כשצריך.\n"
        "להפסקת ההודעות שלחו: הסר"
    ),
    examples=("דנה",),
)

APPROVAL_REQUEST = Template(
    name="arba_approval_request",
    category="UTILITY",
    body="📁 {{1}} · {{2}}\n{{3}}\n\nArba מציעה: {{4}}\nלאשר?",
    examples=(
        "הבית ברעננה",
        "מייל מתאגיד המים",
        "התקבל אישור חיבור למים וביוב.",
        'לתייק תחת "אישור חיבור למים וביוב" ולסמן הושלם',
    ),
    buttons=("✓ אישור", "שינוי באפליקציה"),
)

DAILY_DIGEST = Template(
    name="arba_daily_digest",
    category="UTILITY",
    body=(
        "בוקר טוב {{1}} ☀️\n"
        "{{2}}: {{3}} מתוך {{4}} שלבים הושלמו.\n\n"
        "מה מחכה לך היום: {{5}}\n\n"
        "לכל הפרטים: {{6}}"
    ),
    examples=(
        "דנה",
        "הבית ברעננה",
        "12",
        "44",
        "2 אישורים ממתינים · אפשר להתחיל: בדיקת ברזל לפני יציקה",
        "https://app.arba.co.il/projects/123",
    ),
)

IMPORT_FINISHED = Template(
    name="arba_import_finished",
    category="UTILITY",
    body="🔎 {{1}}: Arba סיימה לסרוק את המייל.\nנמצאו {{2}}.\n{{3}}\n\nלסקירה ולאישור: {{4}}",
    examples=(
        "הבית ברעננה",
        "14 מיילים ו-9 קבצים",
        "חסרים מסמכים ל-3 שלבים שכבר בוצעו.",
        "https://app.arba.co.il/projects/123/import",
    ),
)

DRAFT_READY = Template(
    name="arba_draft_ready",
    category="UTILITY",
    body="✉️ {{1}} · {{2}}\nArba הכינה {{3}}:\n{{4}}\n\nלשלוח?",
    examples=(
        "הבית ברעננה",
        "אישור חיבור למים וביוב מתאגיד המים",
        "פנייה למי רעננה",
        "אישור חיבור למים וביוב – אחוזה 120, רעננה, היתר 20250412",
    ),
    buttons=("✓ שליחה", "עריכה באפליקציה"),
)

DRAFT_READY_PORTAL = Template(
    name="arba_draft_ready_portal",
    category="UTILITY",
    body=(
        "✉️ {{1}} · {{2}}\nArba הכינה {{3}}. הגוף הזה מקבל פניות רק באתר שלו, "
        "אז הנוסח מוכן להדבקה: {{4}}"
    ),
    examples=(
        "הבית ברעננה",
        "אישור כבאות והצלה",
        "פנייה לכבאות והצלה לישראל",
        "https://app.arba.co.il/projects/123#drafts",
    ),
)

ALL = (
    VERIFY_CODE,
    WELCOME,
    APPROVAL_REQUEST,
    DAILY_DIGEST,
    IMPORT_FINISHED,
    DRAFT_READY,
    DRAFT_READY_PORTAL,
)
BY_NAME = {t.name: t for t in ALL}


def clean_param(value: str, limit: int = 600) -> str:
    """Template parameters can't hold line breaks, tabs or runs of spaces."""
    text = re.sub(r"[\r\n\t]+", " · ", value)
    text = re.sub(r" {4,}", "   ", text).strip()
    return text[: limit - 1] + "…" if len(text) > limit else text
