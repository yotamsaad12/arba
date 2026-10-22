"""Keyword classifier: works with no API key, and is the fallback when Claude is unavailable.

It recognises the authority from the sender and text, matches words against requirement titles
and required documents, and reads approval / request / rejection from common Hebrew phrasing.
"""

import re
from collections.abc import Iterable

from app.ai.types import STATUS_FOR_KIND, Decision, Item, RequirementInfo
from app.core.enums import AuthorityType, MessageKind, RequirementStatus
from app.email.parsing import strip_reply_prefixes

AUTHORITY_HINTS: dict[AuthorityType, tuple[str, ...]] = {
    AuthorityType.water_corporation: ("מים", "ביוב", "תאגיד", "water", "mei", 'מז"ח'),
    AuthorityType.home_front_command: ("פיקוד", "העורף", "ממד", 'ממ"ד', "oref", "מוגן"),
    AuthorityType.fire_department: ("כבאות", "כיבוי", "fire", "102"),
    AuthorityType.electrical_inspector: ("חשמל", "electric", 'חח"י'),
    AuthorityType.gas_installer: ("גז", "gas"),
    AuthorityType.testing_lab: ("מעבדה", "דגימות", "בטון", "lab", "מכון", "איטום"),
    AuthorityType.surveyor: ("מודד", "מדידה", "עדות", "survey"),
    AuthorityType.municipality: ("עירייה", "עיריית", "ועדה", "רישוי", "municipality", "היתר"),
    AuthorityType.green_building_lab: ("ירוקה", "5281", "5282", "אנרגטי"),
    AuthorityType.structural_engineer: ("קונסטרוקטור", "קונסטרוקציה"),
}

AUTHORITY_LABELS: dict[AuthorityType, str] = {
    AuthorityType.water_corporation: "תאגיד המים",
    AuthorityType.home_front_command: "פיקוד העורף",
    AuthorityType.fire_department: "כבאות והצלה",
    AuthorityType.electrical_inspector: "בודק חשמל",
    AuthorityType.gas_installer: "מתקין גז",
    AuthorityType.testing_lab: "מעבדה",
    AuthorityType.surveyor: "מודד",
    AuthorityType.municipality: "הרשות המקומית",
    AuthorityType.green_building_lab: "מעבדה לבנייה ירוקה",
    AuthorityType.structural_engineer: "קונסטרוקטור",
}

# Checked in this order: "נדרש להשלים לצורך האישור" is a request even though it says "אישור".
KIND_HINTS: list[tuple[MessageKind, tuple[str, ...]]] = [
    (MessageKind.rejection, ("נדחה", "נדחתה", "לא אושר", "לא אושרה", "דחייה", "rejected")),
    (
        MessageKind.request_for_info,
        ("להשלים", "השלמת", "חסר", "חסרים", "נדרש", "נדרשת", "נדרשים", "יש להעביר", "missing"),
    ),
    (MessageKind.approval, ("מאושר", "אושר", "אושרה", "אישור", "approved", "approval")),
]

STOPWORDS = frozenset({
    "של", "על", "את", "עם", "לפי", "או", "אם", "כל", "לא", "יש", "הוא", "היא", "זה", "זו",
    "מצורף", "מצורפת", "שלום", "רב", "בברכה", "תודה", "עבור", "לצורך", "אנא", "נא", "הנכס",
    "the", "and", "for", "of", "to", "re", "fw", "fwd", "pdf",
})  # fmt: skip
_WORD = re.compile(r"[\w\"׳״']+", re.UNICODE)
_PREFIXES = "והבלמשכ"


def tokens(*texts: str) -> set[str]:
    """Words with their single-letter Hebrew prefixes stripped too (למים -> מים)."""
    out: set[str] = set()
    for text in texts:
        for raw in _WORD.findall(text.lower()):
            word = raw.replace('"', "").replace("״", "").replace("'", "").replace("׳", "")
            if len(word) < 2 or word in STOPWORDS:
                continue
            out.add(word)
            if len(word) > 3 and word[0] in _PREFIXES:
                out.add(word[1:])
    return out - STOPWORDS


def _authorities(text: str) -> set[AuthorityType]:
    lowered = text.lower()
    return {a for a, hints in AUTHORITY_HINTS.items() if any(h in lowered for h in hints)}


def _kind(text: str) -> MessageKind:
    lowered = text.lower()
    for kind, hints in KIND_HINTS:
        if any(h in lowered for h in hints):
            return kind
    return MessageKind.info


def _summary(item: Item, kind: MessageKind) -> str:
    subject = strip_reply_prefixes(item.subject)
    if item.source == "document":
        return f"קובץ חדש: {subject.rsplit('.', 1)[0]}"
    who = item.sender_name or "השולח"
    return {
        MessageKind.approval: f"התקבל אישור מ{who}: {subject}.",
        MessageKind.rejection: f"{who} דחו את הבקשה. צריך לבדוק מה לתקן: {subject}.",
        MessageKind.request_for_info: f"{who} מבקשים להשלים מסמכים או פרטים: {subject}.",
    }.get(kind, f"התקבל עדכון מ{who}: {subject}.")


def classify(item: Item, requirements: Iterable[RequirementInfo]) -> Decision:
    names = " ".join(a.name.rsplit(".", 1)[0] for a in item.attachments)
    sender = f"{item.sender_name or ''} {item.sender_email or ''}"
    full_text = f"{item.subject}\n{item.text}\n{names}"
    words = tokens(item.subject, item.text, names)
    authorities = _authorities(f"{sender} {full_text}")
    kind = _kind(full_text)
    if item.source == "document" and kind != MessageKind.approval:
        # A file named "אישור…" is usually a certificate; other wording means nothing on a file.
        kind = MessageKind.info

    best: tuple[float, RequirementInfo] | None = None
    for r in requirements:
        overlap = len(words & tokens(r.title, " ".join(r.required_documents)))
        score = overlap + (3 if r.authority_type in authorities else 0)
        if r.id == item.current_requirement_id:
            score += 2
        if r.status in (RequirementStatus.done, RequirementStatus.not_applicable):
            score -= 2
        if kind == MessageKind.approval and r.status == RequirementStatus.waiting_for_authority:
            score += 1
        # Earlier requirements win ties: they are what the project is working on.
        key = score - r.order / 1000
        if score >= 3 and (best is None or key > best[0]):
            best = (key, r)

    summary = _summary(item, kind)
    if best is None:
        return Decision(
            requirement_id=item.current_requirement_id,
            kind=kind,
            suggested_status=None,
            summary=summary,
            reason="לא נמצאה דרישה מתאימה בוודאות. בחרו דרישה ידנית.",
            confidence=0.2,
            source="rules",
        )

    score, requirement = best
    authority = AUTHORITY_LABELS.get(requirement.authority_type)
    reason = (
        f'המסמך נראה קשור ל{authority} ולנושא "{requirement.title}".'
        if authority and requirement.authority_type in authorities
        else f'הנושא תואם ל"{requirement.title}".'
    )
    return Decision(
        requirement_id=requirement.id,
        kind=kind,
        suggested_status=STATUS_FOR_KIND[kind],
        summary=summary,
        reason=reason,
        confidence=round(min(0.85, 0.3 + score * 0.07), 2),
        source="rules",
        missing_documents=asked_for(item.text) if kind == MessageKind.request_for_info else [],
    )


_ASKS = re.compile(
    r"(?:יש להשלים|יש להמציא|נא להמציא|נא להשלים|נדרשת?|חסרה?|חסרים)\s*:?\s*([^.\n]{4,120})"
)


def asked_for(text: str) -> list[str]:
    """What an authority's request names: "יש להשלים תוכנית אינסטלציה חתומה" -> that document."""
    found = []
    for match in _ASKS.finditer(text or ""):
        for part in re.split(r",|;| ו(?=[א-ת])", match.group(1)):
            part = re.sub(r"^(?:את|גם)\s+", "", part.strip(" -:"))
            if len(part) >= 4:
                found.append(part)
    return list(dict.fromkeys(found))[:10]
