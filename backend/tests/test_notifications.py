import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select

from app.core.enums import DeliveryChannel, DeliveryStatus
from app.db.models import Delivery, Notification, SimulatedWhatsApp, User
from app.db.session import SessionLocal
from app.modules.notifications.digest import build_digests
from app.modules.notifications.quiet import TZ, quiet_until
from app.whatsapp.phone import mask_phone, normalize_phone
from app.whatsapp.webhook import sign
from app.worker import tick
from tests.conftest import auth
from tests.test_inbox import deliver, email, inbox, setup_project
from tests.test_suggestions import pending

PHONE = "+972501234567"


def il(*args: int) -> datetime:
    return datetime(*args, tzinfo=TZ)  # type: ignore[misc]


# --- quiet hours and phone numbers ----------------------------------------------------


def person(**prefs: bool) -> User:
    return User(quiet_nights=prefs.get("nights", True), quiet_shabbat=prefs.get("shabbat", True))


def test_quiet_hours() -> None:
    # 2026-10-20 is a Tuesday; 2026-10-23 a Friday.
    assert quiet_until(person(), il(2026, 10, 20, 12, 0)) is None
    assert quiet_until(person(), il(2026, 10, 20, 23, 0)) == il(2026, 10, 21, 7, 0)
    assert quiet_until(person(), il(2026, 10, 21, 5, 30)) == il(2026, 10, 21, 7, 0)
    assert quiet_until(person(), il(2026, 10, 23, 17, 0)) == il(2026, 10, 24, 20, 0)
    # Saturday night after Shabbat is still night.
    assert quiet_until(person(), il(2026, 10, 24, 21, 30)) == il(2026, 10, 25, 7, 0)
    assert quiet_until(person(nights=False, shabbat=False), il(2026, 10, 23, 23, 0)) is None


def test_phone_numbers() -> None:
    assert normalize_phone("050-123-4567") == PHONE
    assert normalize_phone("+972 50 123 4567") == PHONE
    assert normalize_phone("972501234567") == PHONE
    assert normalize_phone("+9720501234567") == PHONE
    assert normalize_phone("12") is None
    assert mask_phone(PHONE) == "+972 50-***-4567"


# --- helpers --------------------------------------------------------------------------


async def sim_messages(phone: str = PHONE) -> list[SimulatedWhatsApp]:
    async with SessionLocal() as db:
        return list(
            await db.scalars(
                select(SimulatedWhatsApp)
                .where(SimulatedWhatsApp.phone == phone)
                .order_by(SimulatedWhatsApp.created_at)
            )
        )


async def connect_whatsapp(client: AsyncClient, token: str, phone: str = PHONE) -> None:
    started = await client.post(
        "/api/v1/me/whatsapp/start",
        headers=auth(token),
        json={"phone": phone, "consent": True},
    )
    assert started.status_code == 200, started.text
    code = re.search(r"\d{6}", (await sim_messages(normalize_phone(phone) or ""))[-1].text)
    assert code
    confirmed = await client.post(
        "/api/v1/me/whatsapp/confirm", headers=auth(token), json={"code": code.group(0)}
    )
    assert confirmed.status_code == 200, confirmed.text


async def no_quiet_hours(client: AsyncClient, token: str) -> None:
    await client.patch(
        "/api/v1/me/settings",
        headers=auth(token),
        json={"quiet_nights": False, "quiet_shabbat": False},
    )


async def ready(client: AsyncClient) -> tuple[str, dict[str, Any]]:
    """A project owner with WhatsApp connected and no quiet hours."""
    token, project = await setup_project(client)
    await no_quiet_hours(client, token)
    await connect_whatsapp(client, token)
    return token, project


async def press(client: AsyncClient, token: str, button: dict[str, str]) -> str:
    response = await client.post(
        f"/api/v1/dev/whatsapp/chats/{PHONE}/send",
        headers=auth(token),
        json={"button_id": button["id"], "button_title": button["title"]},
    )
    assert response.status_code == 200, response.text
    return response.json()[-1]["text"]


def soon() -> datetime:
    return datetime.now(UTC) + timedelta(seconds=1)


# --- connecting WhatsApp --------------------------------------------------------------


async def test_connecting_whatsapp_needs_the_code(client: AsyncClient) -> None:
    token, _ = await setup_project(client)
    response = await client.post(
        "/api/v1/me/whatsapp/start",
        headers=auth(token),
        json={"phone": "050-1234567", "consent": True},
    )
    assert response.json() == {"phone": "+972 50-***-4567"}
    assert "קוד האימות" in (await sim_messages())[-1].text

    wrong = await client.post(
        "/api/v1/me/whatsapp/confirm", headers=auth(token), json={"code": "000000"}
    )
    assert wrong.json()["error"]["code"] == "wrong_code"

    await connect_whatsapp(client, token)
    settings = (await client.get("/api/v1/me/settings", headers=auth(token))).json()
    assert settings["whatsapp"] == {
        "connected": True,
        "phone": "+972 50-***-4567",
        "opted_out": False,
    }
    assert "WhatsApp מחובר" in (await sim_messages())[-1].text


async def test_consent_is_required(client: AsyncClient) -> None:
    token, _ = await setup_project(client)
    response = await client.post(
        "/api/v1/me/whatsapp/start", headers=auth(token), json={"phone": PHONE, "consent": False}
    )
    assert response.status_code == 422


# --- notifications and pushes ---------------------------------------------------------


async def test_new_suggestion_reaches_whatsapp_with_buttons(client: AsyncClient) -> None:
    token, project = await ready(client)
    await deliver(client, email(project["inbox_address"]))

    listing = (await client.get("/api/v1/me/notifications", headers=auth(token))).json()
    assert listing["unread"] == 1
    note = listing["items"][0]
    assert (note["kind"], note["urgency"]) == ("approval_needed", "urgent")
    assert {(d["channel"], d["status"]) for d in note["deliveries"]} == {
        ("email", "queued"),
        ("whatsapp", "queued"),
    }

    await tick(soon())
    message = (await sim_messages())[-1]
    assert "Arba מציעה" in message.text and "אישור חיבור למים וביוב" in message.text
    assert [b["title"] for b in message.buttons] == ["✓ אישור", "שינוי באפליקציה"]
    listing = (await client.get("/api/v1/me/notifications", headers=auth(token))).json()
    assert {d["status"] for d in listing["items"][0]["deliveries"]} == {"sent"}


async def test_approving_from_whatsapp_files_and_closes_the_question(client: AsyncClient) -> None:
    token, project = await ready(client)
    await deliver(client, email(project["inbox_address"]))
    await tick(soon())
    approve, _ = (await sim_messages())[-1].buttons

    reply = await press(client, token, approve)
    assert reply.startswith("✅ תויק תחת")
    assert await pending(client, token, project["id"]) == []
    assert (await inbox(client, token, project["id"]))[0]["requirement_title"]
    listing = (await client.get("/api/v1/me/notifications", headers=auth(token))).json()
    assert listing["unread"] == 0

    # Pressing again is harmless.
    assert "כבר טופל" in await press(client, token, approve)


async def test_change_button_sends_a_link(client: AsyncClient) -> None:
    token, project = await ready(client)
    await deliver(client, email(project["inbox_address"]))
    await tick(soon())
    _, change = (await sim_messages())[-1].buttons
    reply = await press(client, token, change)
    assert f"/projects/{project['id']}?tab=inbox&thread=" in reply


async def test_decision_in_the_app_cancels_unsent_pushes(client: AsyncClient) -> None:
    token, project = await ready(client)
    await deliver(client, email(project["inbox_address"]))
    [suggestion] = await pending(client, token, project["id"])
    await client.post(
        f"/api/v1/projects/{project['id']}/suggestions/{suggestion['id']}/dismiss",
        headers=auth(token),
    )
    async with SessionLocal() as db:
        statuses = set(await db.scalars(select(Delivery.status)))
    assert statuses == {DeliveryStatus.skipped}


async def test_quiet_hours_hold_pushes(client: AsyncClient) -> None:
    token, project = await setup_project(client)
    await connect_whatsapp(client, token)
    await client.patch(
        "/api/v1/me/settings",
        headers=auth(token),
        json={"quiet_nights": True, "quiet_shabbat": True},
    )
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == "dana@example.com"))
        assert user is not None
        expected = quiet_until(user, datetime.now(UTC))
    await deliver(client, email(project["inbox_address"]))
    async with SessionLocal() as db:
        due = set(await db.scalars(select(Delivery.due_at)))
    if expected is None:
        assert len(due) == 1  # not quiet right now: due immediately
    else:
        assert due == {expected}


async def test_unconnected_or_opted_out_people_get_no_whatsapp(client: AsyncClient) -> None:
    token, project = await ready(client)
    reply = await client.post(
        f"/api/v1/dev/whatsapp/chats/{PHONE}/send", headers=auth(token), json={"text": "הסר"}
    )
    assert "הוסרת" in reply.json()[-1]["text"]
    await deliver(client, email(project["inbox_address"]))
    await tick(soon())
    async with SessionLocal() as db:
        whatsapp = await db.scalar(
            select(Delivery.status).where(Delivery.channel == DeliveryChannel.whatsapp)
        )
    assert whatsapp == DeliveryStatus.skipped


async def test_unknown_number_is_told_how_to_connect(client: AsyncClient) -> None:
    token, _ = await setup_project(client)
    stranger = "+972521111111"
    response = await client.post(
        f"/api/v1/dev/whatsapp/chats/{stranger}/send", headers=auth(token), json={"text": "שלום"}
    )
    assert "לא מחובר" in response.json()[-1]["text"]


# --- Meta webhook ---------------------------------------------------------------------


async def test_webhook_verification_and_signature(client: AsyncClient) -> None:
    verify = await client.get(
        "/api/v1/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "dev-only-verify-token",
            "hub.challenge": "42",
        },
    )
    assert verify.text == "42"
    bad = await client.post(
        "/api/v1/webhooks/whatsapp", content=b"{}", headers={"x-hub-signature-256": "sha256=nope"}
    )
    assert bad.status_code == 401


async def test_delivery_status_updates_from_meta(client: AsyncClient) -> None:
    token, project = await ready(client)
    await deliver(client, email(project["inbox_address"]))
    await tick(soon())
    message_id = (await sim_messages())[-1].provider_message_id
    status = {"id": message_id, "status": "read"}
    body = json.dumps({"entry": [{"changes": [{"value": {"statuses": [status]}}]}]}).encode()
    response = await client.post(
        "/api/v1/webhooks/whatsapp", content=body, headers={"x-hub-signature-256": sign(body)}
    )
    assert response.status_code == 200
    async with SessionLocal() as db:
        status = await db.scalar(
            select(Delivery.status).where(Delivery.provider_message_id == message_id)
        )
    assert status == DeliveryStatus.read


# --- morning summary ------------------------------------------------------------------


async def test_morning_summary_once_a_day_and_not_on_shabbat(client: AsyncClient) -> None:
    token, project = await ready(client)
    tuesday_morning = il(2026, 10, 20, 7, 10)
    async with SessionLocal() as db:
        assert await build_digests(db, tuesday_morning) == 1
        assert await build_digests(db, tuesday_morning + timedelta(minutes=20)) == 0
        digest = await db.scalar(select(Notification).where(Notification.kind == "daily_digest"))
        assert digest is not None
        assert "אפשר להתחיל" in digest.body
        assert digest.whatsapp and digest.whatsapp["template"] == "arba_daily_digest"
        # Saturday 07:10 is Shabbat for people who keep it (the default).
        await db.execute(Notification.__table__.delete())
        await db.commit()
    await client.patch("/api/v1/me/settings", headers=auth(token), json={"quiet_shabbat": True})
    async with SessionLocal() as db:
        assert await build_digests(db, il(2026, 10, 24, 7, 10)) == 0

    await tick(tuesday_morning + timedelta(minutes=1))
    assert any("בוקר טוב" in m.text for m in await sim_messages())


async def test_notifications_can_be_marked_read(client: AsyncClient) -> None:
    token, project = await ready(client)
    await deliver(client, email(project["inbox_address"]))
    listing = (await client.get("/api/v1/me/notifications", headers=auth(token))).json()
    note_id = listing["items"][0]["id"]
    assert (
        await client.post(f"/api/v1/me/notifications/{note_id}/read", headers=auth(token))
    ).status_code == 204
    other = await client.post(f"/api/v1/me/notifications/{uuid.uuid4()}/read", headers=auth(token))
    assert other.status_code == 404
    assert (await client.get("/api/v1/me/notifications", headers=auth(token))).json()["unread"] == 0


async def test_test_button_sends_now_on_every_channel(client: AsyncClient) -> None:
    token, _ = await setup_project(client)
    # Quiet hours are on by default; a test is sent anyway.
    result = (await client.post("/api/v1/me/notifications/test", headers=auth(token))).json()
    assert {(d["channel"], d["status"]) for d in result} == {
        ("email", "sent"),
        ("whatsapp", "skipped"),
    }
    assert next(d for d in result if d["channel"] == "whatsapp")["error"]

    await connect_whatsapp(client, token)
    result = (await client.post("/api/v1/me/notifications/test", headers=auth(token))).json()
    assert {d["status"] for d in result} == {"sent"}
