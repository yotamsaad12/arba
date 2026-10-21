import base64
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.core.enums import InboundStatus
from app.db.models import InboundEmail
from app.db.session import SessionLocal
from tests.conftest import auth, register
from tests.test_projects import by_title, create_project, requirements

WEBHOOK = "/api/v1/webhooks/postmark/inbound"
CREDENTIALS = (settings.inbound_webhook_user, settings.inbound_webhook_password)
PDF = b"%PDF-1.4\n% test\n"


def email(
    to: str,
    *,
    provider_id: str = "pm-1",
    message_id: str = "<m1@water.co.il>",
    subject: str = "אישור חיבור למים",
    sender: str = "water@water.co.il",
    in_reply_to: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    headers = [{"Name": "Message-ID", "Value": message_id}]
    if in_reply_to:
        headers.append({"Name": "In-Reply-To", "Value": in_reply_to})
    return {
        "MessageID": provider_id,
        "FromFull": {"Email": sender, "Name": "תאגיד המים"},
        "ToFull": [{"Email": to}],
        "Subject": subject,
        "Date": "Wed, 21 Oct 2026 10:00:00 +0300",
        "TextBody": "שלום, מצורף האישור.",
        "Headers": headers,
        "Attachments": attachments
        if attachments is not None
        else [
            {
                "Name": "אישור חיבור.pdf",
                "Content": base64.b64encode(PDF).decode(),
                "ContentType": "application/pdf",
            }
        ],
        **extra,
    }


async def deliver(client: AsyncClient, payload: dict[str, Any]) -> dict[str, str]:
    response = await client.post(WEBHOOK, json=payload, auth=CREDENTIALS)
    assert response.status_code == 200, response.text
    return response.json()


async def setup_project(client: AsyncClient) -> tuple[str, dict[str, Any]]:
    token = await register(client)
    return token, await create_project(client, token)


async def inbox(client: AsyncClient, token: str, project_id: str) -> list[dict[str, Any]]:
    return (await client.get(f"/api/v1/projects/{project_id}/inbox", headers=auth(token))).json()


async def test_webhook_requires_credentials(client: AsyncClient) -> None:
    response = await client.post(WEBHOOK, json={}, auth=("postmark", "wrong"))
    assert response.status_code == 401
    assert (await client.post(WEBHOOK, json={})).status_code == 401


async def test_email_lands_in_project_inbox_with_attachment(client: AsyncClient) -> None:
    token, project = await setup_project(client)
    logo = {"Name": "logo.png", "Content": base64.b64encode(b"png").decode(),
            "ContentType": "image/png", "ContentID": "logo@sig"}  # fmt: skip
    pdf = email(project["inbox_address"])["Attachments"][0]
    # Recipient case differs from the stored address on purpose.
    payload = email(project["inbox_address"].upper(), attachments=[pdf, logo])
    assert (await deliver(client, payload)) == {"status": "accepted"}

    threads = await inbox(client, token, project["id"])
    assert len(threads) == 1
    thread = threads[0]
    assert (thread["subject"], thread["unread_count"], thread["attachment_count"]) == (
        "אישור חיבור למים",
        1,
        1,  # the inline signature logo is not a document
    )
    detail = (await client.get(f"/api/v1/projects/{project['id']}", headers=auth(token))).json()
    assert detail["inbox"] == {"unread": 1, "unfiled": 1, "pending_suggestions": 1}

    full = (
        await client.get(
            f"/api/v1/projects/{project['id']}/threads/{thread['id']}", headers=auth(token)
        )
    ).json()
    attachment = full["messages"][0]["attachments"][0]
    assert attachment["file_name"] == "אישור חיבור.pdf"
    download = await client.get(attachment["download_url"])
    assert download.content == PDF
    assert download.headers["content-disposition"].startswith("attachment;")


async def test_redelivery_is_ignored(client: AsyncClient) -> None:
    token, project = await setup_project(client)
    payload = email(project["inbox_address"])
    await deliver(client, payload)
    assert (await deliver(client, payload)) == {"status": "duplicate"}
    # Same Message-ID through a different provider delivery id (e.g. sent to two addresses).
    await deliver(client, {**payload, "MessageID": "pm-other"})
    threads = await inbox(client, token, project["id"])
    assert [t["message_count"] for t in threads] == [1]


async def test_unknown_address_is_kept_as_unroutable(client: AsyncClient) -> None:
    await setup_project(client)
    await deliver(client, email("nobody@in.arba.co.il", provider_id="pm-lost"))
    async with SessionLocal() as db:
        inbound = await db.scalar(
            select(InboundEmail).where(InboundEmail.provider_message_id == "pm-lost")
        )
    assert inbound is not None and inbound.status == InboundStatus.unroutable


async def test_replies_join_their_thread(client: AsyncClient) -> None:
    token, project = await setup_project(client)
    to = project["inbox_address"]
    await deliver(client, email(to))
    # Threaded by headers.
    await deliver(
        client,
        email(
            to,
            provider_id="pm-2",
            message_id="<m2@x>",
            in_reply_to="<m1@water.co.il>",
            subject="something else entirely",
        ),  # fmt: skip
    )
    # No headers, but a Hebrew reply prefix on the same subject from the same sender.
    await deliver(client, email(to, provider_id="pm-3", message_id="<m3@x>",
                                subject="השב: אישור חיבור למים"))  # fmt: skip
    # Same subject from someone else is a different conversation.
    await deliver(client, email(to, provider_id="pm-4", message_id="<m4@x>",
                                sender="fire@fire.gov.il"))  # fmt: skip

    threads = await inbox(client, token, project["id"])
    assert sorted(t["message_count"] for t in threads) == [1, 3]


async def test_filing_a_thread_files_its_attachments(client: AsyncClient) -> None:
    token, project = await setup_project(client)
    to = project["inbox_address"]
    await deliver(client, email(to))
    thread = (await inbox(client, token, project["id"]))[0]
    water = by_title(await requirements(client, token, project["id"]), "אישור חיבור למים")

    response = await client.patch(
        f"/api/v1/projects/{project['id']}/threads/{thread['id']}",
        headers=auth(token),
        json={"requirement_id": water["id"]},
    )
    assert response.status_code == 200
    assert response.json()["requirement_title"] == water["title"]

    # A later reply's attachment follows the filing automatically.
    await deliver(client, email(to, provider_id="pm-2", message_id="<m2@x>",
                                in_reply_to="<m1@water.co.il>"))  # fmt: skip
    water = by_title(await requirements(client, token, project["id"]), "אישור חיבור למים")
    assert water["document_count"] == 2

    docs = (
        await client.get(
            f"/api/v1/projects/{project['id']}/documents",
            params={"requirement_id": water["id"]},
            headers=auth(token),
        )
    ).json()
    assert {d["source"] for d in docs} == {"email"}


async def test_reading_marks_thread_read(client: AsyncClient) -> None:
    token, project = await setup_project(client)
    await deliver(client, email(project["inbox_address"]))
    thread = (await inbox(client, token, project["id"]))[0]
    url = f"/api/v1/projects/{project['id']}/threads/{thread['id']}/read"
    assert (await client.post(url, headers=auth(token))).status_code == 204
    assert (await inbox(client, token, project["id"]))[0]["unread_count"] == 0


async def test_other_users_cannot_read_the_inbox(client: AsyncClient) -> None:
    _, project = await setup_project(client)
    await deliver(client, email(project["inbox_address"]))
    stranger = await register(client, email="other@example.com")
    response = await client.get(f"/api/v1/projects/{project['id']}/inbox", headers=auth(stranger))
    assert response.status_code == 404
