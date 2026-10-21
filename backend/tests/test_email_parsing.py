import base64

from app.email.parsing import (
    html_to_text,
    message_ids,
    normalize_message_id,
    normalize_subject,
    parse_postmark,
)


def test_subject_prefixes_in_english_and_hebrew_are_removed() -> None:
    assert normalize_subject("RE: Fwd: אישור חיבור למים") == "אישור חיבור למים"
    assert normalize_subject("השב: הועבר: בקשה להשלמת מסמכים") == "בקשה להשלמת מסמכים"
    assert normalize_subject("RE[2]:  Permit   Request") == "permit request"


def test_message_ids_are_normalized() -> None:
    assert normalize_message_id("<ABC@Mail.Example>") == "abc@mail.example"
    assert message_ids("<a@x> <B@y>\r\n <c@z>") == ["a@x", "b@y", "c@z"]
    assert normalize_message_id(None) is None


def test_html_bodies_become_plain_text_without_scripts() -> None:
    html = (
        "<html><head><style>p{}</style></head><body>"
        "<p>שלום</p><script>alert(1)</script><p>אישור מצורף</p></body></html>"
    )
    assert html_to_text(html) == "שלום\n\nאישור מצורף"


def test_parse_postmark_payload() -> None:
    email = parse_postmark(
        {
            "MessageID": "pm-1",
            "FromFull": {"Email": "Water@Corp.co.il", "Name": "תאגיד המים"},
            "ToFull": [{"Email": "P-ABC@in.arba.co.il"}],
            "CcFull": [],
            "OriginalRecipient": "p-abc@in.arba.co.il",
            "Subject": "אישור חיבור",
            "Date": "Wed, 21 Oct 2026 10:00:00 +0300",
            "TextBody": "",
            "HtmlBody": "<p>מצורף האישור</p>",
            "Headers": [
                {"Name": "Message-ID", "Value": "<M1@corp.co.il>"},
                {"Name": "In-Reply-To", "Value": "<out-1@arba.co.il>"},
            ],
            "Attachments": [
                {
                    "Name": "אישור.pdf",
                    "Content": base64.b64encode(b"%PDF-1.4").decode(),
                    "ContentType": "application/pdf",
                }
            ],
        }
    )
    assert email.message_id == "m1@corp.co.il"
    assert email.in_reply_to == "out-1@arba.co.il"
    assert email.from_email == "water@corp.co.il"
    assert email.recipients == ["p-abc@in.arba.co.il"]
    assert email.text == "מצורף האישור"
    assert email.attachments[0].data == b"%PDF-1.4"
    assert email.sent_at.utcoffset() is not None
