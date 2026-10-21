"""Sends a Postmark-shaped email to the local inbound webhook, for trying the inbox without
a mail provider.

    python -m app.scripts.send_test_email p-abcd2345@in.arba.co.il
    python -m app.scripts.send_test_email p-abcd2345@in.arba.co.il --attach plan.pdf --reply
"""

import argparse
import base64
import mimetypes
import uuid
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path

import httpx

from app.core.config import settings

SAMPLES = {
    "water": (
        "water@mei-raanana.co.il",
        "תאגיד המים",
        "אישור חיבור למים וביוב",
        "שלום רב,\n\nמצורף אישור החיבור למים וביוב עבור הנכס.\n"
        "האישור בתוקף לשנה.\n\nבברכה,\nמחלקת חיבורים",
    ),
    "hfc": (
        "mamad@oref.org.il",
        "פיקוד העורף",
        'בקשה להשלמת מסמכים - ממ"ד',
        "שלום,\n\nלצורך מתן האישור נדרש להשלים: "
        "צילום ברזל לפני יציקה ותעודת בדיקת אטימות.\n\nבברכה",
    ),
}


def sample_pdf(title: str) -> bytes:
    """A small valid one-page PDF."""
    stream = f"BT /F1 18 Tf 72 720 Td ({title}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("to", help="the project's inbox address")
    parser.add_argument("--sample", choices=SAMPLES, default="water")
    parser.add_argument("--attach", type=Path, nargs="*", default=[], help="files to attach")
    parser.add_argument("--reply", action="store_true", help="send as a reply in the same thread")
    parser.add_argument("--url", default="http://localhost:8000/api/v1/webhooks/postmark/inbound")
    args = parser.parse_args()

    sender, name, subject, body = SAMPLES[args.sample]
    attachments = [
        {
            "Name": f"{subject}.pdf",
            "Content": base64.b64encode(sample_pdf(f"Arba test: {args.sample}")).decode(),
            "ContentType": "application/pdf",
        }
    ]
    for path in args.attach:
        attachments.append(
            {
                "Name": path.name,
                "Content": base64.b64encode(path.read_bytes()).decode(),
                "ContentType": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            }
        )

    message_id = f"<{uuid.uuid4()}@{sender.split('@')[1]}>"
    payload = {
        "MessageID": str(uuid.uuid4()),
        "FromFull": {"Email": sender, "Name": name},
        "ToFull": [{"Email": args.to}],
        "OriginalRecipient": args.to,
        "Subject": f"השב: {subject}" if args.reply else subject,
        "Date": format_datetime(datetime.now(UTC)),
        "TextBody": body,
        "Headers": [{"Name": "Message-ID", "Value": message_id}],
        "Attachments": attachments,
    }
    response = httpx.post(
        args.url,
        json=payload,
        auth=(settings.inbound_webhook_user, settings.inbound_webhook_password),
        timeout=30,
    )
    print(response.status_code, response.text)


if __name__ == "__main__":
    main()
