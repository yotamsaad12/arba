"""Professionals upload through a personal link, and Arba checks every document."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.core.enums import CheckVerdict
from app.db.models import DocumentRequest
from app.db.session import SessionLocal
from app.modules.checks import checker
from app.modules.checks.checker import CheckResult, Facts, with_rules
from app.modules.team.service import remind_open
from tests.conftest import auth, register
from tests.test_documents import upload
from tests.test_permits_directory import RAANANA, new_project
from tests.test_projects import by_title, requirements
from tests.test_suggestions import pending

SURVEY = "סימון המבנה במגרש על ידי מודד מוסמך"
PDF = b"%PDF-1.4 survey"


async def survey_step(client: AsyncClient, token: str, project_id: str) -> dict[str, Any]:
    return by_title(await requirements(client, token, project_id), SURVEY)


async def ask_surveyor(
    client: AsyncClient, token: str, project_id: str, **contact: Any
) -> dict[str, Any]:
    step = await survey_step(client, token, project_id)
    response = await client.post(
        f"/api/v1/projects/{project_id}/document-requests",
        headers=auth(token),
        json={
            "requirement_id": step["id"],
            "contact": {"role": "surveyor", "name": "משה המודד", **contact},
            "documents": step["required_documents"],
            "note": "בבקשה עם חותמת",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def professional_uploads(client: AsyncClient, link_token: str, name: str) -> dict[str, Any]:
    base = f"/api/v1/public/requests/{link_token}"
    started = await client.post(
        f"{base}/uploads",
        json={"file_name": name, "content_type": "application/pdf", "size_bytes": len(PDF)},
    )
    assert started.status_code == 201, started.text
    target = started.json()["upload"]
    put = await client.request(
        target["method"], target["url"], content=PDF, headers=target["headers"]
    )
    assert put.status_code == 204, put.text
    done = await client.post(f"{base}/uploads/{started.json()['document_id']}/complete")
    assert done.status_code == 200, done.text
    return done.json()


async def test_a_professional_uploads_without_an_account(client: AsyncClient) -> None:
    token = await register(client)
    project = await new_project(client, token, locality_code=RAANANA, gush="6587")
    request = await ask_surveyor(
        client, token, project["id"], email="moshe@modedim.co.il", phone="050-1234567"
    )
    assert set(request["sent_by"]) == {"email", "whatsapp"}
    assert request["contact"]["phone"] == "+972501234567"
    link_token = request["link"].rsplit("/r/", 1)[1]

    # The professional's page: what is asked, for which project; no login.
    page = (await client.get(f"/api/v1/public/requests/{link_token}")).json()
    assert (page["contact_name"], page["requirement_title"]) == ("משה המודד", SURVEY)
    assert page["note"] == "בבקשה עם חותמת" and page["documents"]

    await professional_uploads(client, link_token, "מפת סימון.pdf")
    finished = await client.post(f"/api/v1/public/requests/{link_token}/done")
    assert finished.status_code == 204

    # Filed straight into the step, credited to the professional, and checked.
    docs = (
        await client.get(f"/api/v1/projects/{project['id']}/documents", headers=auth(token))
    ).json()
    [doc] = docs
    step = await survey_step(client, token, project["id"])
    assert (doc["requirement_id"], doc["source"], doc["uploaded_by_name"]) == (
        step["id"],
        "professional",
        "משה המודד",
    )
    assert doc["check_status"] is not None

    requests = (
        await client.get(f"/api/v1/projects/{project['id']}/document-requests", headers=auth(token))
    ).json()
    assert requests[0]["status"] == "fulfilled" and len(requests[0]["files"]) == 1
    kinds = {
        n["kind"]
        for n in (await client.get("/api/v1/me/notifications", headers=auth(token))).json()["items"]
    }
    assert "document_received" in kinds

    # The team remembers the surveyor for next time.
    team = (
        await client.get(f"/api/v1/projects/{project['id']}/contacts", headers=auth(token))
    ).json()
    assert [c["name"] for c in team] == ["משה המודד"]


async def test_links_that_stopped_working(client: AsyncClient) -> None:
    token = await register(client)
    project = await new_project(client, token, locality_code=RAANANA)
    request = await ask_surveyor(client, token, project["id"], email="moshe@modedim.co.il")
    link_token = request["link"].rsplit("/r/", 1)[1]
    assert (await client.get("/api/v1/public/requests/not-a-token")).status_code == 404
    await client.post(
        f"/api/v1/projects/{project['id']}/document-requests/{request['id']}/cancel",
        headers=auth(token),
    )
    assert (await client.get(f"/api/v1/public/requests/{link_token}")).status_code == 404


async def test_open_requests_are_sent_again(client: AsyncClient) -> None:
    token = await register(client)
    project = await new_project(client, token, locality_code=RAANANA)
    await ask_surveyor(client, token, project["id"], email="moshe@modedim.co.il")
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        assert await remind_open(db, now) == 0  # too early
        await db.execute(update(DocumentRequest).values(last_sent_at=now - timedelta(days=4)))
        await db.commit()
        assert await remind_open(db, now) == 1
    requests = (
        await client.get(f"/api/v1/projects/{project['id']}/document-requests", headers=auth(token))
    ).json()
    assert requests[0]["sent_count"] == 2


async def test_a_good_document_proposes_marking_the_step_done(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fine(_name: str, _type: str, _data: bytes, facts: Facts) -> CheckResult:
        return CheckResult(
            verdict=CheckVerdict.ok,
            satisfies=facts.required_documents,
            signed="yes",
            stamped="yes",
            project_match="yes",
            summary="מפת סימון חתומה של הפרויקט.",
        )

    monkeypatch.setattr(checker, "check", fine)
    token = await register(client)
    project = await new_project(client, token, locality_code=RAANANA)
    step = await survey_step(client, token, project["id"])
    await upload(client, token, project["id"], name="מפת סימון.pdf", requirement_id=step["id"])
    [suggestion] = await pending(client, token, project["id"])
    assert (suggestion["requirement_id"], suggestion["suggested_status"]) == (step["id"], "done")


async def test_a_problem_is_reported_and_shown_on_the_step(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def wrong(*_: Any) -> CheckResult:
        return CheckResult(
            verdict=CheckVerdict.problem,
            issues=["רשום במסמך גוש 6590, והפרויקט בגוש 6587"],
            summary="המסמך שייך לנכס אחר.",
        )

    monkeypatch.setattr(checker, "check", wrong)
    token = await register(client)
    project = await new_project(client, token, locality_code=RAANANA)
    step = await survey_step(client, token, project["id"])
    await upload(client, token, project["id"], name="מפה.pdf", requirement_id=step["id"])
    step = await survey_step(client, token, project["id"])
    assert step["check_issues"] == ["⛔ מפה.pdf: רשום במסמך גוש 6590, והפרויקט בגוש 6587"]
    assert await pending(client, token, project["id"]) == []
    kinds = {
        n["kind"]
        for n in (await client.get("/api/v1/me/notifications", headers=auth(token))).json()["items"]
    }
    assert "document_problem" in kinds


def _facts(**kw: Any) -> Facts:
    base: dict[str, Any] = dict(
        requirement_title=SURVEY,
        requirement_description=None,
        required_documents=["מפת סימון"],
        address=None,
        locality="רעננה",
        gush="6587",
        helka="112",
        permit_number="20250412",
        today=date(2026, 10, 23),
    )
    return Facts(**(base | kw))


def test_rules_catch_another_property_and_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.permits import extraction

    monkeypatch.setattr(extraction, "_pdf_text", lambda _: "מפת סימון\nגוש: 6590 חלקה: 112")
    result = with_rules("מפת סימון.pdf", "application/pdf", b"%PDF", _facts())
    assert result.verdict == CheckVerdict.problem and result.project_match == "no"
    assert result.satisfies == ["מפת סימון"]

    monkeypatch.setattr(
        extraction, "_pdf_text", lambda _: "אישור בודק\nגוש: 6587\nבתוקף עד: 01/03/2026"
    )
    result = with_rules("אישור.pdf", "application/pdf", b"%PDF", _facts())
    assert result.verdict == CheckVerdict.problem
    assert any("פג תוקף" in i for i in result.issues)

    monkeypatch.setattr(extraction, "_pdf_text", lambda _: "מפת סימון היתר 20250412")
    assert with_rules("m.pdf", "application/pdf", b"%PDF", _facts()).verdict == CheckVerdict.ok
