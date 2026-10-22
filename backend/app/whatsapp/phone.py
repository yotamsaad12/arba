import re

_DIGITS = re.compile(r"\D")


def normalize_phone(raw: str) -> str | None:
    """E.164 (+972501234567) from what people type: 050-123-4567, 972501234567, +972 50…

    Local numbers without a country code are taken as Israeli.
    """
    text = raw.strip()
    digits = _DIGITS.sub("", text)
    if not digits:
        return None
    if text.startswith("+"):
        number = digits
    elif digits.startswith("00"):
        number = digits[2:]
    elif digits.startswith("0"):
        number = "972" + digits[1:]
    else:
        number = digits
    if number.startswith("9720"):
        number = "972" + number[4:]
    if not 10 <= len(number) <= 15:
        return None
    return "+" + number


def mask_phone(phone: str) -> str:
    """+972501234567 -> +972 50-***-4567, for showing which number is connected."""
    if phone.startswith("+972") and len(phone) == 13:
        return f"+972 {phone[4:6]}-***-{phone[-4:]}"
    return f"{phone[:4]}***{phone[-4:]}"
