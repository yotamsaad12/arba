"""Arba writes to the approving bodies, the person approves, and Arba follows up."""

from datetime import UTC, date, datetime, timedelta
from email.message import EmailMessage
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.core.config import settings
from app.db.models import Notification, OutboundDraft
from app.db.session import SessionLocal
from app.modules.outreach import service as outreach
from tests.conftest import auth, register
from tests.test_inbox import deliver, email
from tests.test_permits_directory import RAANANA, new_project, upload_permit
from tests.test_projects import by_title, requirements

HAIFA = 4000
FORM4_LIST = "קבלת רשימת האישורים לטופס 4 מהרשות"


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[EmailMessage]:
    sent: list[EmailMessage] = []

    async def capture(message: EmailMessage) -> bool:
        sent.append(message)
        return True

    monkeypatch.setattr(outreach, "send_email", capture)
    return sent


async def checked_project(client: AsyncClient, token: str, locality: int) -> dict[str, Any]:
    """A project whose permit checks out, so Arba may write to authorities."""
    project = await new_project(
        client,
        token,
        locality_code=locality,
        address="רחוב הנשיא 10",
        gush="10811",
        helka="5",
        permit_number="20250099",
        permit_issue_date=(date.today() - timedelta(days=30)).isoformat(),
    )
    await upload_permit(client, token, project["id"])
    await client.post(f"/api/v1/projects/{project['id']}/permit/check", headers=auth(token))
    return project


async def draft_for(client: AsyncClient, token: str, project_id: str, title: str) -> dict[str, Any]:
    step = by_title(await requirements(client, token, project_id), title)
    response = await client.post(
        f"/api/v1/projects/{project_id}/requirements/{step['id']}/drafts",
        headers=auth(token),
        json={},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_request_goes_to_the_official_address_and_the_reply_comes_back(
    client: AsyncClient, outbox: list[EmailMessage]
) -> None:
    token = await register(client)
    project = await checked_project(client, token, HAIFA)
    draft = await draft_for(client, token, project["id"], FORM4_LIST)
    assert (draft["channel"], draft["to_email"], draft["recipient_source"]) == (
        "email",
        "rishuybnia@haifa.muni.il",
        "official_site",
    )
    assert "10811" in draft["body"] and "20250099" in draft["subject"]
    # The permit is attached.
    assert [a["file_name"] for a in draft["attachments"]] == ["היתר.pdf"]

    edited = await client.patch(
        f"/api/v1/projects/{project['id']}/drafts/{draft['id']}",
        headers=auth(token),
        json={"body": draft["body"] + "\nנשמח לתשובה בהקדם."},
    )
    assert "בהקדם" in edited.json()["body"]

    sent = await client.post(
        f"/api/v1/projects/{project['id']}/drafts/{draft['id']}/send", headers=auth(token)
    )
    assert sent.status_code == 200, sent.text
    [message] = outbox
    assert (
        message["To"] == "רישוי בנייה <rishuybnia@haifa.muni.il>" or "rishuybnia" in message["To"]
    )
    assert message["Reply-To"] == project["inbox_address"]
    assert message["Cc"] == "dana@example.com"
    assert "בהקדם" in message.get_body(("plain",)).get_content()  # type: ignore[union-attr]
    assert [p.get_filename() for p in message.iter_attachments()] == ["היתר.pdf"]

    step = by_title(await requirements(client, token, project["id"]), FORM4_LIST)
    assert step["status"] == "waiting_for_authority"

    # The committee answers the email: it joins the same conversation.
    await deliver(
        client,
        email(
            project["inbox_address"],
            sender="rishuybnia@haifa.muni.il",
            subject=f"RE: {draft['subject']}",
            message_id="<reply-1@haifa.muni.il>",
            in_reply_to=message["Message-ID"],
        ),
    )
    threads = (
        await client.get(f"/api/v1/projects/{project['id']}/inbox", headers=auth(token))
    ).json()
    [thread] = [t for t in threads if t["requirement_id"] == step["id"]]
    assert thread["message_count"] == 2


async def test_website_only_bodies_get_text_to_paste(client: AsyncClient) -> None:
    token = await register(client)
    project = await checked_project(client, token, RAANANA)
    draft = await draft_for(client, token, project["id"], FORM4_LIST)
    assert draft["channel"] == "portal" and draft["portal_url"]
    refused = await client.post(
        f"/api/v1/projects/{project['id']}/drafts/{draft['id']}/send", headers=auth(token)
    )
    assert refused.json()["error"]["code"] == "draft_not_email"
    done = await client.post(
        f"/api/v1/projects/{project['id']}/drafts/{draft['id']}/submitted", headers=auth(token)
    )
    assert done.json()["status"] == "sent"


async def test_arba_drafts_ready_steps_once_the_permit_checks_out(client: AsyncClient) -> None:
    token = await register(client)
    unchecked = await new_project(client, token, locality_code=HAIFA)
    project = await checked_project(client, token, HAIFA)
    async with SessionLocal() as db:
        assert await outreach.prepare_requests(db, limit=50) > 0
        drafts = list(await db.scalars(select(OutboundDraft)))
    assert {str(d.project_id) for d in drafts} == {project["id"]}
    titles = {
        d["requirement_title"]
        for d in (
            await client.get(f"/api/v1/projects/{project['id']}/drafts", headers=auth(token))
        ).json()
    }
    assert FORM4_LIST in titles
    # Never a letter about the permit itself; in-person steps aren't drafted.
    assert not any(t.startswith("היתר בנייה") or t == "תיק תוכניות מאושר" for t in titles)
    assert unchecked["id"] not in {str(d.project_id) for d in drafts}

    notifications = (await client.get("/api/v1/me/notifications", headers=auth(token))).json()
    assert "draft_ready" in {n["kind"] for n in notifications["items"]}

    # Running again drafts nothing new.
    async with SessionLocal() as db:
        assert await outreach.prepare_requests(db, limit=50) == 0


async def test_silence_brings_a_reminder_then_a_call(
    client: AsyncClient, outbox: list[EmailMessage]
) -> None:
    token = await register(client)
    project = await checked_project(client, token, HAIFA)
    draft = await draft_for(client, token, project["id"], FORM4_LIST)
    sent = await client.post(
        f"/api/v1/projects/{project['id']}/drafts/{draft['id']}/send", headers=auth(token)
    )
    assert sent.status_code == 200, sent.text
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        assert await outreach.prepare_reminders(db, now) == 0  # too early
        await db.execute(update(OutboundDraft).values(sent_at=now - timedelta(days=8)))
        await db.commit()
        assert await outreach.prepare_reminders(db, now) == 1
    [reminder] = (
        await client.get(f"/api/v1/projects/{project['id']}/drafts", headers=auth(token))
    ).json()
    assert reminder["kind"] == "reminder" and reminder["subject"].startswith("תזכורת")
    assert reminder["to_email"] == "rishuybnia@haifa.muni.il"

    # Three reminders without an answer: Arba suggests calling instead.
    async with SessionLocal() as db:
        for _ in range(3):
            pending = await db.scalar(select(OutboundDraft).where(OutboundDraft.status == "draft"))
            if pending is None:
                await outreach.prepare_reminders(db, now)
                pending = await db.scalar(
                    select(OutboundDraft).where(OutboundDraft.status == "draft")
                )
            assert pending is not None
            pending.status, pending.sent_at = "sent", now - timedelta(days=8)
            await db.commit()
        await db.execute(update(OutboundDraft).values(sent_at=now - timedelta(days=8)))
        await db.commit()
        assert await outreach.prepare_reminders(db, now) == 0
        titles = list(await db.scalars(select(Notification.title)))
    assert any("לא עונים" in t for t in titles)


async def test_test_mail_never_reaches_a_real_authority(
    client: AsyncClient, outbox: list[EmailMessage], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "email_allowed_recipients", ["me@example.com"])
    token = await register(client)
    project = await checked_project(client, token, HAIFA)
    draft = await draft_for(client, token, project["id"], FORM4_LIST)
    await client.post(
        f"/api/v1/projects/{project['id']}/drafts/{draft['id']}/send", headers=auth(token)
    )
    [message] = outbox
    assert "me@example.com" in message["To"] and "rishuybnia" not in message["To"]
    assert message["Subject"].startswith("[בדיקה, במקום אל rishuybnia@haifa.muni.il]")
    assert message["Cc"] is None
